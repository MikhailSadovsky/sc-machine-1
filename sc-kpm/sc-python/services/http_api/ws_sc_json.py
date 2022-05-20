
import tornado

from tornado import websocket
from sc import *

import json
import sys
import traceback
import threading

clients = []


class EventHandler:

  def __init__(self):
    self.evt_native = None
    self.send_func = None

  def Set(self, evt, func):
    self.evt_native = evt
    self.send_func = func

  def OnEmit(self, evt):
    self.send_func(evt)


class ScJsonSocketHandler(websocket.WebSocketHandler):

  def initialize(self, evt_manager, ioloop):
    self.events = {}
    self.event_manager = evt_manager
    self.alive = False
    self.ioloop = ioloop

  def check_origin(self, origin):
    return True

  def open(self):
    if self not in clients:
      clients.append(self)
    self.alive = True

  def on_close(self):
    if self in clients:
      clients.remove(self)
    self.alive = False

    # remove all events
    for eid, evt in self.events.items():
      self.event_manager.DestroyEvent(evt.evt_native)
    self.events.clear()

  def on_message(self, msg):
    params = json.loads(msg)
    status = False

    ctx = ScMemoryContext.Create(str(self))
    try:
      request_type = params['type']
      request_payload = params['payload']

      response_payload = None
      if request_type == 'keynodes':
        response_payload = self.handleKeynodes(ctx, request_payload)
      elif request_type == 'create_elements':
        response_payload = self.handleCreateElements(ctx, request_payload)
      elif request_type == 'check_elements':
        response_payload = self.handleCheckElements(ctx, request_payload)
      elif request_type == 'delete_elements':
        response_payload = self.handleDeleteElements(ctx, request_payload)
      elif request_type == 'search_template':
        response_payload = self.handleTemplateSearch(ctx, request_payload)
      elif request_type == 'generate_template':
        response_payload = self.handleTemplateGenerate(ctx, request_payload)
      elif request_type == 'content':
        response_payload = self.handleContent(ctx, request_payload)
      elif request_type == 'events':
        response_payload = self.handleEvents(ctx, request_payload)

      if response_payload is not None:
        status = True
      else:
        response_payload = "Unsupported request type: {}".format(request_type)
    except ValueError as err:
      response_payload = str(err)
    except RuntimeError as ex:
      response_payload = str(ex).split('File')[0]
      print("Unexpected error:", response_payload)
    finally:
      pass

    # make and send response
    response = {
        'id': params['id'],
        'event': False,
        'status': status,
        'payload': response_payload
    }

    self.sendMessage(json.dumps(response))

  def sendMessage(self, msg):
    self.write_message(msg)

  def handleKeynodes(self, ctx, payload):
    result = [0] * len(payload)

    idx = 0
    for cmd in payload:
      cmdType = cmd['command']
      idtf = cmd['idtf']

      if cmdType == 'find':
        result[idx] = ctx.HelperResolveSystemIdtf(idtf, ScType.Unknown).ToInt()
      elif cmdType == 'resolve':
        elType = ScType(cmd['elType'])
        result[idx] = ctx.HelperResolveSystemIdtf(idtf, elType).ToInt()

      idx += 1

    return result

  def handleCreateElements(self, ctx, payload):

    result = [0] * len(payload)

    idx = 0
    for cmd in payload:
      el = cmd['el']
      elType = ScType(cmd['type'])

      if el == 'node':
        result[idx] = ctx.CreateNode(elType).ToInt()

      elif el == 'edge':

        def resolveAdjAddr(obj):
          value = obj['value']
          if obj['type'] == 'ref':
            return ScAddr(result[value])

          return ScAddr(value)

        src = resolveAdjAddr(cmd['src'])
        trg = resolveAdjAddr(cmd['trg'])

        result[idx] = ctx.CreateEdge(elType, src, trg).ToInt()

      elif el == 'link':
        # TODO: support link type
        addr = ctx.CreateLink()
        if addr.IsValid():
          ctx.SetLinkContent(addr, cmd['content'])
        result[idx] = addr.ToInt()

      idx += 1

    return result

  def handleCheckElements(self, ctx, payload):
    result = [0] * len(payload)

    idx = 0
    for value in payload:
      addr = ScAddr(value)
      if addr.IsValid():
        result[idx] = ctx.GetElementType(addr).ToInt()

      idx += 1

    return result

  def handleDeleteElements(self, ctx, payload):

    for value in payload:
      ctx.DeleteElement(ScAddr(value))

    return True

  def makeTemplate(self, triples):

    def convert_value(value):

      t = value['type']
      v = value['value']
      result = v

      if t == 'type':
        result = ScType(v)
      elif t == 'addr':
        result = ScAddr(v)

      if 'alias' in value:
        alias = value['alias']
        result = result >> alias

      return result

    templ = ScTemplate()
    for triple in triples:
      src = convert_value(triple[0])
      edg = convert_value(triple[1])
      trg = convert_value(triple[2])
      templ.Triple(src, edg, trg)

    return templ

  def handleTemplateSearch(self, ctx, payload):
    templ = None
    if 'templ' in payload:
      templ = self.buildTemplate(ctx, payload['templ'], payload['params'])
    else:
      templ = self.buildTemplate(ctx, payload)
    # run search
    search_result = ctx.HelperSearchTemplate(templ)
    aliases = search_result.Aliases()
    
    addrs = []
    for idx in range(search_result.Size()):
      result_item = search_result[idx]
      items = [0] * result_item.Size()
      for it in range(len(items)):
        items[it] = search_result[idx][it].ToInt()
      addrs.append(items)

    return {
        'aliases': aliases,
        'addrs': addrs
    }

  def handleTemplateGenerate(self, ctx, payload):
    
    templ = None
    templ_params = ScTemplateParams()
    if 'templ' in payload:
      templ = self.buildTemplate(ctx, payload['templ'])
      templ_params = self.buildTemplateParams(ctx, payload['params'])
    else:
      templ = self.buildTemplate(ctx, payload)

    # run search
    gen_result = ctx.HelperGenTemplate(templ, templ_params)
    if not gen_result:
      return None

    addrs = []
    for idx in range(gen_result.Size()):
      addrs.append(gen_result[idx].ToInt())

    return {
      "aliases": gen_result.Aliases(),
      "addrs": addrs
    }

  def handleContent(self, ctx, payload):
    result = []
    for cmd in payload:
      t = cmd['command']

      if t == 'set':
        a = ScAddr(cmd['addr'])
        value = self.getContentTypeValue(cmd['type'], cmd['data'])
        result.append(ctx.SetLinkContent(a, value))
        
      elif t == 'get':
        a = ScAddr(cmd['addr'])
        content = ctx.GetLinkContent(a)
        value = None
        ctype = None
        if content:
          ctype = content.GetType()

          if ctype == ScLinkContent.Int:
            value = content.AsInt()
            ctype = 'int'
          elif ctype == ScLinkContent.Float:
            value = content.AsFloat()
            ctype = 'float'
          elif ctype == ScLinkContent.String:
            value = content.AsString()
            ctype = 'string'

        result.append({
            'value': value,
            'type': ctype
        })

      elif t == 'find':
        value = cmd['data']
        addrs = ctx.FindLinksByContent(value)
        result.append([addr.ToInt() for addr in addrs])

    return result

  def onEmitEvent(self, evt):
    response = {
        'id': evt.id,
        'event': True,
        'status': True,
        'payload': [evt.addr.ToInt(), evt.edge_addr.ToInt(), evt.other_addr.ToInt()]
    }
    data = json.dumps(response)
    self.ioloop.add_callback(self.sendMessage, data)

  def handleEvents(self, ctx, payload):
    result = []
    createEvents = None
    try:
      createEvents = payload['create']
    except KeyError:
      pass

    if createEvents:
      for evt in createEvents:
        # determine function that will be create events
        evtType = evt['type']
        createFunc = None
        if evtType == 'add_outgoing_edge':
          createFunc = self.event_manager.CreateEventAddOutputEdge
        elif evtType == 'add_ingoing_edge':
          createFunc = self.event_manager.CreateEventAddInputEdge
        elif evtType == 'remove_outgoing_edge':
          createFunc = self.event_manager.CreateEventRemoveOutputEdge
        elif evtType == 'remove_ingoing_edge':
          createFunc = self.event_manager.CreateEventRemoveInputEdge
        elif evtType == 'content_change':
          createFunc = self.event_manager.CreateEventContentChanged
        elif evtType == 'delete_element':
          createFunc = self.event_manager.CreateEventEraseElement

        assert createFunc != None

        addr = ScAddr(evt['addr'])

        evt_handler = EventHandler()
        evt = createFunc(addr, evt_handler.OnEmit)
        evt_handler.Set(evt, self.onEmitEvent)

        self.events[evt.GetID()] = evt_handler
        result.append(evt.GetID())

    return result

  def buildTemplate(self, ctx, templPayload, params=None):

    if isinstance(templPayload, str):
      # build from SCs
      return ctx.HelperBuildTemplate(templPayload)
    elif 'type' in templPayload:
      templ_params = self.buildTemplateParams(ctx, params)
      type = templPayload['type']
      if type == 'addr':
        # build from SC-structure ScAddr
        addr_value = templPayload['value']
        addr = ScAddr(addr_value)
        type = ctx.GetElementType(addr)
        if type.IsUnknown():
          raise ValueError(f"template with addr value {addr_value} doesn't exist")
        elif not type == ScType.NodeConstStruct:
          raise ValueError(f"element with addr value {addr_value} isn't structure")
        return ctx.HelperBuildTemplate(addr, templ_params)
      elif type == 'idtf':
        # build from SC-structure identifier
        idtf = templPayload['value']
        addr = ctx.HelperResolveSystemIdtf(idtf, ScType.Unknown)
        if not addr.IsValid():
          raise ValueError(f"template with identifier {idtf} doesn't exist")
        return ctx.HelperBuildTemplate(addr, templ_params)
    else:
      # build from template triples
      return self.makeTemplate(templPayload)

  def buildTemplateParams(self, ctx, params):
    templ_params = ScTemplateParams()
    if params:
      for alias, value in params.items():
        if isinstance(value, str):
          # param is an identifier
          addr = ctx.HelperResolveSystemIdtf(value, ScType.Unknown)
          if not addr.IsValid():
            raise ValueError(f"element with identifier {value} doesn't exist")
          templ_params.Add(alias, addr)
        elif isinstance(value, int):
          # param is ScAddr value
          templ_params.Add(alias, ScAddr(value))
        else:
          # param is link content that should be generated
          data = self.getContentTypeValue(value['type'], value['data'])
          link = ctx.CreateLink()
          ctx.SetLinkContent(link, data)
          templ_params.Add(alias, link)

    return templ_params

  def getContentTypeValue(self, content_type, value):
    if content_type == 'float':
      value = float(value)
    elif content_type == 'int':
      value = int(value)
    elif content_type == 'string':
      value = str(value)

    return value