from tornado import httpserver, testing, web, websocket, gen
from unittest import TestLoader, TestCase, TextTestRunner

import json
import types
import tornado
import http_api.ws_sc_json as wsh

from common import ScModule

from sc import *

module = None


class WsJsonApiTest(testing.AsyncTestCase):

  def setUp(self):
    super(WsJsonApiTest, self).setUp()

    ioloop = tornado.ioloop.IOLoop.instance()

    app = web.Application([
        (r"/", wsh.ScJsonSocketHandler, {'evt_manager': module.events, 'ioloop': ioloop}),
    ])
    server = httpserver.HTTPServer(app)
    socket, self.port = testing.bind_unused_port()
    server.add_socket(socket)

  def make_connection(self):
    return websocket.websocket_connect(
        'ws://localhost:{}/'.format(self.port)
    )

  @gen.coroutine
  def cmd_create_elements(self, client, params):

    payload = []
    for p in params:
      if 'data' in p:
        payload.append({
            'el': 'link',
            'type': p['type'].ToInt(),
            'content': p['data']
        })
      elif ('src' in p) and ('trg' in p):

        def convert(v):
          res = {}
          if isinstance(v, ScAddr):
            res = {
                'type': 'addr',
                'value': v.ToInt()
            }
          else:
            res = {
                'type': 'ref',
                'value': v
            }
          return res

        payload.append({
            'el': 'edge',
            'src': convert(p['src']),
            'trg': convert(p['trg']),
            'type': p['type'].ToInt()
        })
      else:
        payload.append({
            'el': 'node',
            'type': p['type'].ToInt()
        })

    client.write_message(self.makeRequest(1, 'create_elements', payload))

    # check response
    response = yield client.read_message()

    return json.loads(response)

  @gen.coroutine
  def cmd_check_elements(self, client, params):
    client.write_message(self.makeRequest(1, 'check_elements', params))
    response = yield client.read_message()
    return json.loads(response)

  @gen.coroutine
  def cmd_delete_elements(self, client, params):
    client.write_message(self.makeRequest(1, 'delete_elements', params))
    response = yield client.read_message()
    return json.loads(response)

  @gen.coroutine
  def cmd_search_template(self, client, template, params=None):

    def convert_value(v):
      if isinstance(v, ScAddr):
        return {
            'type': 'addr',
            'value': v.ToInt()
        }
      elif isinstance(v, ScType):
        return {
            'type': 'type',
            'value': v.ToInt()
        }

      return {
          'type': 'alias',
          'value': v
      }

    template_payload = []
    payload = {}
    if isinstance(template, list):
      for p in template:
        item = []
        self.assertTrue(len(p) >= 3)
        for i in p[:3]:
          v = None
          if type(i) is list:
            self.assertEqual(len(i), 2)
            v = convert_value(i[0])
            v['alias'] = i[1]
          else:
            v = convert_value(i)
          item.append(v)

        # append options
        if len(p) == 4:
          item.append(p[-1])

        template_payload.append(item)
    elif isinstance(template, str):
      template_payload = {
        'type': 'idtf',
        'value': template
      }
    else:
      template_payload = {
        'type': 'addr',
        'value': template
      }

    if params:
      payload['templ'] = template_payload
      payload['params'] = params
    else:
      payload = template_payload
    client.write_message(self.makeRequest(1, 'search_template', payload))
    response = yield client.read_message()
    return json.loads(response)

  @gen.coroutine
  def cmd_generate_template(self, client, template, params=None):

    def convert_value(v):
      if isinstance(v, ScAddr):
        return {
            'type': 'addr',
            'value': v.ToInt()
        }
      elif isinstance(v, ScType):
        return {
            'type': 'type',
            'value': v.ToInt()
        }

      return {
          'type': 'alias',
          'value': v
      }

    payload = {}
    if isinstance(template, list):
      triples = []
      for p in template:
        item = []
        self.assertEqual(len(p), 3)
        for i in p:
          v = None
          if type(i) is list:
            self.assertEqual(len(i), 2)
            v = convert_value(i[0])
            v['alias'] = i[1]
          else:
            v = convert_value(i)
          item.append(v)

        triples.append(item)
        payload = triples
    elif isinstance(template, str):
      payload = {
        'type': 'idtf',
        'value': template
      }
    else:
      payload = {
        'type': 'addr',
        'value': template
      }

    if params:
      client.write_message(self.makeRequest(1, 'generate_template', {
          'templ': payload,
          'params': params
      }))
    else:
      client.write_message(self.makeRequest(1, 'generate_template', payload))
    response = yield client.read_message()
    return json.loads(response)

  @gen.coroutine
  def cmd_events(self, client, create, delete):
    client.write_message(self.makeRequest(1, 'events', {
        'create': create, 'delete': delete
    }))
    response = yield client.read_message()
    return json.loads(response)

  @gen.coroutine
  def cmd_content(self, client, commands):
    client.write_message(self.makeRequest(1, 'content', commands))
    response = yield client.read_message()
    return json.loads(response)

  @testing.gen_test
  def test_connect(self):
    c = yield self.make_connection()

    self.assertIsNotNone(c)

  def makeRequest(self, reqID, reqType, payload):
    return json.dumps({
        "id": reqID,
        "type": reqType,
        "payload": payload
    })

  @testing.gen_test
  def test_keynodes(self):
    client = yield self.make_connection()

    self.assertIsNotNone(client)

    # make request
    notFindIdtf = "Not find"
    resolveIdtf = "Resolve idtf"
    requestID = 1
    payload = [
        {
            "command": "find",
            "idtf": notFindIdtf
        },
        {
            "command": "resolve",
            "idtf": resolveIdtf,
            "elType": ScType.NodeConst.ToInt()
        }
    ]

    # send request
    client.write_message(self.makeRequest(requestID, 'keynodes', payload))
    response = yield client.read_message()

    resObj = json.loads(response)
    resPayload = resObj['payload']

    self.assertEqual(resObj['id'], requestID)
    self.assertTrue(resObj['status'])
    self.assertEqual(len(resPayload), len(payload))
    self.assertEqual(resPayload[0], 0)
    self.assertNotEqual(resPayload[1], 0)

  @testing.gen_test
  def test_keynodes_error(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    # make error request
    payload = [
        {
            "command": 'find'
        }
    ]

    client.write_message(self.makeRequest(1, 'keyndes', payload))
    response = yield client.read_message()

    resObj = json.loads(response)
    self.assertEqual(resObj['id'], 1)
    self.assertFalse(resObj['status'])

  @testing.gen_test
  def test_unsupported_command(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    client.write_message(self.makeRequest(1, 'unknown', {}))

    response = yield client.read_message()
    resObj = json.loads(response)

    self.assertEqual(resObj['id'], 1)
    self.assertFalse(resObj['status'])

  @testing.gen_test
  def test_create_elements(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    # create keynode
    client.write_message(self.makeRequest(3, 'keynodes', [
        {
            "command": "resolve",
            "idtf": "any idtf 1",
            "elType": ScType.NodeConst.ToInt()
        }]))

    response = yield client.read_message()
    resObj = json.loads(response)

    keynode = resObj['payload'][0]
    self.assertTrue(resObj['status'])
    self.assertNotEqual(keynode, 0)

    keynode = ScAddr(keynode)

    # create elements
    params = [
        {
            'type': ScType.Node
        },
        {
            'type': ScType.LinkConst,
            'data': 45.4
        },
        {
            'type': ScType.LinkConst,
            'data': 45
        },
        {
            'type': ScType.LinkConst,
            'data': "test content"
        },
        {
            "src": 0,
            'trg': keynode,
            'type': ScType.EdgeAccessConstPosPerm
        }
    ]

    resObj = yield self.cmd_create_elements(client, params)

    self.assertTrue(resObj['status'])
    results = resObj['payload']
    for addr in results:
      self.assertNotEqual(addr, 0)

  @testing.gen_test
  def test_check_elements(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    elements = yield self.cmd_create_elements(client, [
        {
            'type': ScType.Node
        },
        {
            'type': ScType.Link,
            'data': 'test data'
        }])

    elements = elements['payload']

    params = [elements[0], 0, elements[1]]
    resObj = yield self.cmd_check_elements(client, params)

    resPayload = resObj['payload']

    self.assertTrue(resObj['status'])
    self.assertEqual(len(resPayload), len(params))
    self.assertEqual(resPayload[0], ScType.Node.ToInt())
    self.assertEqual(resPayload[1], 0)
    self.assertEqual(resPayload[2], ScType.LinkConst.ToInt())

  @testing.gen_test
  def test_delete_elements(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    types = [
        ScType.Node,
        ScType.NodeConstAbstract,
        ScType.NodeConstClass
    ]
    params = []
    for t in types:
      params.append({'type': t})

    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']

    # check elements
    types2 = yield self.cmd_check_elements(client, elements)
    types2 = types2['payload']
    self.assertEqual(len(types), len(types2))
    for idx in range(len(types)):
      self.assertEqual(types[idx].ToInt(), types2[idx])

    resObj = yield self.cmd_delete_elements(client, elements)
    self.assertTrue(resObj['status'])

    types2 = yield self.cmd_check_elements(client, elements)
    types2 = types2['payload']
    self.assertEqual(len(types), len(types2))
    for idx in range(len(types)):
      self.assertEqual(0, types2[idx])

  @testing.gen_test
  def test_template_search(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    # create construction for a test
    # ..0 ~> ..3: ..1;;
    # ..0 ~> ..3: ..2;;
    params = [
        {
            'type': ScType.NodeConst
        },
        {
            'type': ScType.NodeConst
        },
        {
            'type': ScType.NodeConst
        },
        {
            'type': ScType.NodeConstClass
        },
        {
            'type': ScType.EdgeAccessConstPosTemp,
            'src': 0,
            'trg': 1
        },
        {
            'type': ScType.EdgeAccessConstPosTemp,
            'src': 0,
            'trg': 2
        },
        {
            'type': ScType.EdgeAccessConstPosTemp,
            'src': 3,
            'trg': 4
        },
        {
            'type': ScType.EdgeAccessConstPosTemp,
            'src': 3,
            'trg': 5
        }
    ]
    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']

    self.assertEqual(len(elements), len(params))

    # ..0 _~> ..3: _node;;
    templ = [
        [
            ScAddr(elements[0]),
            [ScType.EdgeAccessVarPosTemp, "_edge"],
            [ScType.NodeVar, "_node"]
        ],
        [
            ScAddr(elements[3]),
            ScType.EdgeAccessVarPosTemp,
            "_edge"
        ]
    ]
    result = yield self.cmd_search_template(client, templ)
    self.assertTrue(result['status'])
    result = result['payload']

    aliases = result['aliases']
    addrs = result['addrs']

    self.assertEqual(len(addrs), 2)

    self.assertTrue('_node' in aliases)
    self.assertTrue('_edge' in aliases)

    _node = aliases['_node']
    _edge = aliases['_edge']

    _nodes_list = [addrs[0][_node], addrs[1][_node]]
    _edges_list = [addrs[0][_edge], addrs[1][_edge]]

    self.assertTrue(elements[1] in _nodes_list)
    self.assertTrue(elements[2] in _nodes_list)

    self.assertTrue(elements[4] in _edges_list)
    self.assertTrue(elements[5] in _edges_list)

  @testing.gen_test
  def test_template_search_by_struct(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)
    test_template_idtf = 'test_template_0'
    payload = [
      {
        "command": "resolve",
        "idtf": "_node",
        "elType": ScType.NodeVar.ToInt()
      },
      {
        "command": "resolve",
        "idtf": test_template_idtf,
        "elType": ScType.NodeConstStruct.ToInt()
      }
    ]

    # create var for template with _node alias and template struct node
    client.write_message(self.makeRequest(1, 'keynodes', payload))
    response = yield client.read_message()

    resObj = json.loads(response)
    keynode = resObj['payload'][0]
    test_template_value = resObj['payload'][1]
    self.assertTrue(resObj['status'])
    self.assertNotEqual(keynode, 0)
    self.assertNotEqual(test_template_value, 0)

    keynode = ScAddr(keynode)
    test_template = ScAddr(test_template_value)

    # create elements for template search and search result construction
    params = [
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.EdgeAccessVarPosPerm,
        'src': 0,
        'trg': keynode
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': test_template,
        'trg': 0
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': test_template,
        'trg': keynode
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': test_template,
        'trg': 2
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 0,
        'trg': 1
      }
    ]
    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']
    self.assertEqual(len(elements), len(params))

    def check_search_results(result):
      self.assertTrue(result['status'])
      result = result['payload']
      aliases = result['aliases']
      addrs = result['addrs']
      self.assertEqual(len(addrs), 1)
      self.assertTrue('_node' in aliases)
      _node = aliases['_node']
      self.assertEqual(elements[1], addrs[0][_node])
      self.assertEqual(elements[6], addrs[0][1])

    # search by struct addr
    result = yield self.cmd_search_template(client, test_template_value)
    check_search_results(result)

    # search by struct identifier
    result = yield self.cmd_search_template(client, test_template_idtf)
    check_search_results(result)

  @testing.gen_test
  def test_template_search_by_struct_with_param(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    test_param_idtf = 'test_param'
    payload = [
      {
        "command": "resolve",
        "idtf": "_node",
        "elType": ScType.NodeVar.ToInt()
      },
      {
        "command": "resolve",
        "idtf": test_param_idtf,
        "elType": ScType.NodeConst.ToInt()
      }
    ]

    # create var for template with _node alias
    client.write_message(self.makeRequest(1, 'keynodes', payload))
    response = yield client.read_message()

    resObj = json.loads(response)
    keynode = resObj['payload'][0]
    test_param_value = resObj['payload'][1]
    self.assertTrue(resObj['status'])
    self.assertNotEqual(keynode, 0)
    self.assertNotEqual(test_param_value, 0)

    keynode = ScAddr(keynode)
    test_param = ScAddr(test_param_value)

    # create struct for template search and search result construction
    params = [
      {
        'type': ScType.NodeConstStruct
      },
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.EdgeAccessVarPosPerm,
        'src': 1,
        'trg': keynode
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 0,
        'trg': 1
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 0,
        'trg': keynode
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 0,
        'trg': 3
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 1,
        'trg': 2
      },
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 1,
        'trg': 8
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 1,
        'trg': test_param
      },
    ]
    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']
    template = elements[0]
    self.assertEqual(len(elements), len(params))

    # search by struct addr without params - expect 2 search results
    result = yield self.cmd_search_template(client, template)
    self.assertTrue(result['status'])
    result = result['payload']
    aliases = result['aliases']
    addrs = result['addrs']

    self.assertEqual(len(addrs), 3)
    self.assertTrue('_node' in aliases)

    _node = aliases['_node']
    _nodes_list = [addrs[0][_node], addrs[1][_node], addrs[2][_node]]
    self.assertTrue(elements[2] in _nodes_list)
    self.assertTrue(elements[8] in _nodes_list)
    self.assertTrue(test_param_value in _nodes_list)

    def verify_search_result(result, expected_addr):
      self.assertTrue(result['status'])
      result = result['payload']
      addrs = result['addrs']
      self.assertEqual(len(addrs), 1)
      self.assertEqual(expected_addr, addrs[0][2])

    # search by struct addr with ScAddr as param
    result = yield self.cmd_search_template(client, template, {'_node': elements[2]})
    verify_search_result(result, elements[2])

    # search by struct addr with system identifier as param
    result = yield self.cmd_search_template(client, template, {'_node': test_param_idtf})
    verify_search_result(result, test_param_value)

  @testing.gen_test
  def test_template_generate(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    # create construction for a test
    # ..0 ~> ..3: ..1;;
    # ..0 ~> ..3: ..2;;
    params = [
        {
            'type': ScType.NodeConst
        },
        {
            'type': ScType.NodeConst
        }
    ]
    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']

    self.assertEqual(len(elements), len(params))

    # ..0 _~> ..3: _node;;
    templ = [
        [
            ScAddr(elements[0]),
            [ScType.EdgeAccessVarPosPerm, '_edge'],
            [ScType.NodeVar, '_node']
        ],
        [
            '_node',
            ScType.EdgeAccessVarPosTemp,
            '_edge'
        ]
    ]

    result = yield self.cmd_search_template(client, templ)
    self.assertTrue(result['status'])
    result = result['payload']

    addrs = result['addrs']

    # have no any construction
    self.assertEqual(len(addrs), 0)

    # generate new construction
    result = yield self.cmd_generate_template(client, templ, {
        '_node': elements[1]
    })
    self.assertTrue(result['status'])
    result = result['payload']
    aliases = result['aliases']
    addrs = result['addrs']

    def get_by_alias(alias):
      return addrs[aliases[alias]]

    self.assertNotEqual(get_by_alias('_edge'), 0)

    # try to search generated construction
    result = yield self.cmd_search_template(client, templ)
    self.assertTrue(result['status'])
    result = result['payload']

    aliases = result['aliases']
    addrs = result['addrs']

    self.assertEqual(len(addrs), 1)
    self.assertEqual(addrs[0][aliases['_node']], elements[1])

    # invalid params
    result = yield self.cmd_generate_template(client, templ, {
        '_edge': elements[1]
    })
    self.assertFalse(result['status'])

  @testing.gen_test
  def test_template_generate_by_struct(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    test_template_idtf = 'test_template_1'
    payload = [
      {
        "command": "resolve",
        "idtf": test_template_idtf,
        "elType": ScType.NodeConstStruct.ToInt()
      }
    ]

    # create template struct
    client.write_message(self.makeRequest(1, 'keynodes', payload))
    response = yield client.read_message()

    resObj = json.loads(response)
    test_template_value = resObj['payload'][0]
    self.assertTrue(resObj['status'])
    self.assertNotEqual(test_template_value, 0)

    test_template = ScAddr(test_template_value)

    # create template construction
    params = [
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.NodeVar
      },
      {
        'type': ScType.EdgeAccessVarPosPerm,
        'src': 0,
        'trg': 1
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': test_template,
        'trg': 0
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': test_template,
        'trg': 1
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': test_template,
        'trg': 2
      }
    ]
    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']
    self.assertEqual(len(elements), len(params))

    # search by template struct addr
    result = yield self.cmd_search_template(client, test_template_value)
    self.assertTrue(result['status'])
    result = result['payload']

    addrs = result['addrs']

    # have no any construction
    self.assertEqual(len(addrs), 0)

    # generate new construction by template addr
    result = yield self.cmd_generate_template(client, test_template_value)
    self.assertTrue(result['status'])
    result = result['payload']
    addrs = result['addrs']
    expected = addrs[2]

    # try to search generated construction
    result = yield self.cmd_search_template(client, test_template_value)
    self.assertTrue(result['status'])
    result = result['payload']
    addrs = result['addrs']

    self.assertEqual(len(addrs), 1)
    self.assertEqual(addrs[0][2], expected)

    # generate new construction by template identifier
    result = yield self.cmd_generate_template(client, test_template_idtf)
    self.assertTrue(result['status'])

    # try to search generated construction
    result = yield self.cmd_search_template(client, test_template_value)
    self.assertTrue(result['status'])
    result = result['payload']
    addrs = result['addrs']

    self.assertEqual(len(addrs), 2)

  @testing.gen_test
  def test_template_generate_by_struct_with_param(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    test_param_idtf = 'test_param_0'
    payload = [
      {
        "command": "resolve",
        "idtf": "_node",
        "elType": ScType.NodeVar.ToInt()
      },
      {
        "command": "resolve",
        "idtf": test_param_idtf,
        "elType": ScType.NodeConst.ToInt()
      }
    ]

    # create var for template with _node alias
    client.write_message(self.makeRequest(1, 'keynodes', payload))
    response = yield client.read_message()

    resObj = json.loads(response)
    keynode = resObj['payload'][0]
    test_param_value = resObj['payload'][1]
    self.assertTrue(resObj['status'])
    self.assertNotEqual(keynode, 0)
    self.assertNotEqual(test_param_value, 0)

    keynode = ScAddr(keynode)
    test_param = ScAddr(test_param_value)

    # create struct for template search and search result construction
    params = [
      {
        'type': ScType.NodeConstStruct
      },
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 0,
        'trg': 1
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 0,
        'trg': keynode
      },
      {
        'type': ScType.EdgeAccessVarPosPerm,
        'src': 1,
        'trg': keynode
      },
      {
        'type': ScType.EdgeAccessConstPosPerm,
        'src': 0,
        'trg': 4
      }
    ]
    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']
    template = elements[0]
    self.assertEqual(len(elements), len(params))

    # search by struct addr without params - expect results not found
    result = yield self.cmd_search_template(client, template)
    self.assertTrue(result['status'])
    result = result['payload']
    addrs = result['addrs']
    self.assertEqual(len(addrs), 0)

    def verify_generation_result(result):
      self.assertTrue(result['status'])
      result = result['payload']
      addrs = result['addrs']
      aliases = result['aliases']
      self.assertEqual(len(addrs), 3)
      self.assertEqual(test_param_value, addrs[aliases['_node']])

    # generate by struct addr with ScAddr as param
    result = yield self.cmd_generate_template(client, template, {'_node': test_param_value})
    verify_generation_result(result)

    # generate by struct addr with system identifier as param
    result = yield self.cmd_generate_template(client, template, {'_node': test_param_idtf})
    verify_generation_result(result)

    # search by struct addr all generation results
    result = yield self.cmd_search_template(client, template)
    self.assertTrue(result['status'])
    result = result['payload']

    addrs = result['addrs']
    aliases = result['aliases']

    self.assertEqual(len(addrs), 2)
    self.assertTrue('_node' in aliases)
    _node = aliases['_node']
    _nodes_list = [addrs[0][_node], addrs[1][_node]]
    self.assertEqual(test_param_value, _nodes_list[0])
    self.assertEqual(test_param_value, _nodes_list[1])

  @testing.gen_test
  def test_template_generate_by_struct_with_specified_link_content(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    params = [
      {
        'type': ScType.NodeConst
      },
      {
        'type': ScType.NodeConstClass
      }
    ]
    elements = yield self.cmd_create_elements(client, params)
    elements = elements['payload']

    self.assertEqual(len(elements), len(params))

    # ..0 _~> ..3: _link;;
    templ = [
      [
        ScAddr(elements[0]),
        [ScType.EdgeAccessVarPosTemp, "_edge"],
        [ScType.LinkVar, "_link"]
      ],
      [
        ScAddr(elements[1]),
        ScType.EdgeAccessVarPosTemp,
        "_edge"
      ]
    ]

    # search by template without params - expect results not found
    result = yield self.cmd_search_template(client, templ)
    self.assertTrue(result['status'])
    result = result['payload']
    addrs = result['addrs']
    self.assertEqual(len(addrs), 0)

    test_link_content = 'test_string'
    # generate by template with specified string link content
    generated_result = yield self.cmd_generate_template(client, templ, {
      '_link': {'data': test_link_content, 'type': 'str'}
    })
    self.assertTrue(generated_result['status'])
    generated_result = generated_result['payload']
    generated_addrs = generated_result['addrs']
    aliases = generated_result['aliases']
    self.assertEqual(len(generated_addrs), 6)

    result = yield self.cmd_content(client,[{'command': 'get', 'addr': generated_addrs[aliases['_link']]}])
    self.assertTrue(result['status'])
    result = result['payload']

    self.assertEqual(result[0]['value'], test_link_content)
    self.assertEqual(result[0]['type'], 'string')

    # search by template generation results and verify results
    search_result = yield self.cmd_search_template(client, templ)
    self.assertTrue(search_result['status'])
    search_result = search_result['payload']
    self.assertEqual(generated_addrs, search_result['addrs'][0])

  # @testing.gen_test
  # def test_events(self):
  #     client = yield self.make_connection()
  #     self.assertIsNotNone(client)

  #     elements = yield self.cmd_create_elements(client, [
  #         {
  #             'type': ScType.Node
  #         },
  #         {
  #             'type': ScType.Link,
  #             'data': 'test data'
  #         }])

  #     elements = elements['payload']
  #     self.assertNotEqual(elements[0], 0)
  #     self.assertNotEqual(elements[1], 0)

  #     # TODO: implement events testing

  @testing.gen_test
  def test_content(self):
    client = yield self.make_connection()
    self.assertIsNotNone(client)

    elements = yield self.cmd_create_elements(client, [
        {
            'type': ScType.Node
        },
        {
            'type': ScType.Link,
            'data': 45
        }])

    elements = elements['payload']
    self.assertNotEqual(elements[0], 0)
    self.assertNotEqual(elements[1], 0)

    # TODO: implement events testing
    commands = [
        {'command': 'get', 'addr': elements[0]},
        {'command': 'get', 'addr': elements[1]}
    ]

    result = yield self.cmd_content(client, commands)
    self.assertTrue(result['status'])
    result = result['payload']

    self.assertFalse(result[0]['value'])
    self.assertEqual(result[1]['value'], 45)
    self.assertEqual(result[1]['type'], 'int')


def RunTest(test):
  global TestLoader, TextTestRunner
  testItem = TestLoader().loadTestsFromTestCase(test)
  res = TextTestRunner(verbosity=2).run(testItem)

  if not res.wasSuccessful():
    raise Exception("Unit test failed")


class TestModule(ScModule):
  def __init__(self):
    ScModule.__init__(self,
                      ctx=__ctx__,
                      cpp_bridge=__cpp_bridge__,
                      keynodes=[
                      ])

  def DoTests(self):
    try:
      RunTest(WsJsonApiTest)
    except Exception as ex:
      raise ex
    except:
      import sys
      print("Unexpected error:", sys.exc_info()[0])
    finally:
      self.Stop()

  def OnInitialize(self, params):
    self.DoTests()

  def OnShutdown(self):
    pass


module = TestModule()
module.Run()
