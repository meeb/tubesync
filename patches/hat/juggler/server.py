"""Juggler server"""

from collections.abc import Iterable
import asyncio
import logging
import pathlib
import ssl
import typing

import aiohttp.hdrs
import aiohttp.web

from hat import aio
from hat import json

from hat.juggler.basic_auth import BasicAuthMiddleware
from hat.juggler.transport import Transport


mlog: logging.Logger = logging.getLogger(__name__)
"""Module logger"""

ConnectionCb: typing.TypeAlias = aio.AsyncCallable[['Connection'], None]
"""Connection callback"""

RequestCb: typing.TypeAlias = aio.AsyncCallable[['Connection', str, json.Data],
                                                json.Data]
"""Request callback"""


async def listen(host: str,
                 port: int,
                 connection_cb: ConnectionCb | None = None,
                 request_cb: RequestCb | None = None,
                 *,
                 ws_path: str | None = '/ws',
                 static_dir: pathlib.PurePath | None = None,
                 index_path: str | None = '/index.html',
                 htpasswd_file: pathlib.PurePath | None = None,
                 ssl_ctx: ssl.SSLContext | None = None,
                 autoflush_delay: float | None = 0.2,
                 shutdown_timeout: float = 0.1,
                 state: json.Storage | None = None,
                 parallel_requests: bool = False,
                 additional_routes: Iterable[aiohttp.web.RouteDef] = [],
                 send_queue_size: int = 1024,
                 max_segment_size: int = 64 * 1024,
                 ping_delay: float = 30,
                 ping_timeout: float = 30,
                 no_cache: bool = True
                 ) -> 'Server':
    """Create listening server

    Each time server receives new incoming juggler connection, `connection_cb`
    is called with newly created connection.

    For each connection, when server receives `request` message, `request_cb`
    is called with associated connection, request name and request data.
    If `request_cb` returns value, successful `response` message is sent
    with resulting value as data. If `request_cb` raises exception,
    unsuccessful `response` message is sent with raised exception as data.
    If `request_cb` is ``None``, each `request` message causes sending
    of unsuccessful `response` message.

    If `static_dir` is set, server serves static files is addition to providing
    juggler communication.

    If `index_path` is set, request for url path ``/`` are redirected to
    `index_path`.

    If `htpasswd_file` is set, HTTP Basic Authentication is enabled.
    All requests are checked for ``Authorization`` header and only users
    specified by `htpassword_file` are accepted. `htpasswd_file` is read
    during initialization and changes to it's content, after initialization
    finishes, are not monitored.

    If `ssl_ctx` is set, server provides `https/wss` communication instead
    of `http/ws` communication.

    Argument `autoflush_delay` is associated with all connections associated
    with this server. `autoflush_delay` defines maximum time delay for
    automatic synchronization of `state` changes. If `autoflush_delay` is set
    to ``None``, automatic synchronization is disabled and user is responsible
    for calling :meth:`Connection.flush`. If `autoflush_delay` is set to ``0``,
    synchronization of `state` is performed on each change of `state` data.

    `shutdown_timeout` defines maximum time duration server will wait for
    regular connection close procedures during server shutdown. All connections
    that are not closed during this period are forcefully closed.

    If `state` is ``None``, each connection is initialized with it's own
    instance of server state. If `state` is set, provided state is shared
    between all connections.

    If `parallel_requests` is set to ``True``, incoming requests will be
    processed in parallel - processing of subsequent requests can start (and
    finish) before prior responses are generated.

    Argument `additional_routes` can be used for providing addition aiohttp
    route definitions handled by running web server.

    `send_queue_size` limits number of messages that can be put in send queue.
    This limit can impact blocking of :meth:`Connection.notify`.

    `max_segment_size` limits maximum size of single segment
    (transport payload size).

    When connection doesn't receive incoming data,
    `ping_delay` is time (in seconds) that connection waits before sending
    ping request.

    `ping_timeout` is time (in seconds), that connection waits for any kind
    of incoming traffic before closed connection is assumed.

    If `no_cache` is set to ``True``, server will include
    ``Cache-Control: no-cache`` header in all responses.

    Args:
        host: listening hostname
        port: listening TCP port
        connection_cb: connection callback
        request_cb: request callback
        ws_path: WebSocket url path segment
        static_dir: static files directory path
        index_path: index path
        htpasswd_file: htpasswd file path
        ssl_ctx: SSL context
        autoflush_delay: autoflush delay
        shutdown_timeout: shutdown timeout
        state: shared server state
        parallel_requests: parallel request processing
        additional_routes: additional route definitions
        send_queue_size: send queue size
        max_segment_size: maximum segment size
        ping_delay: ping delay
        ping_timeout: ping timeout
        no_cache: no cache header

    """
    server = Server()
    server._connection_cb = connection_cb
    server._request_cb = request_cb
    server._autoflush_delay = autoflush_delay
    server._state = state
    server._parallel_requests = parallel_requests
    server._send_queue_size = send_queue_size
    server._max_segment_size = max_segment_size
    server._ping_delay = ping_delay
    server._ping_timeout = ping_timeout
    server._async_group = aio.Group()

    middlewares = []

    if htpasswd_file:
        middlewares.append(BasicAuthMiddleware(htpasswd_file))

    routes = []

    if ws_path:
        routes.append(aiohttp.web.get(ws_path, server._ws_handler))

    if index_path:

        async def root_handler(request):
            raise aiohttp.web.HTTPFound(index_path)

        routes.append(aiohttp.web.get('/', root_handler))

    routes.extend(additional_routes)

    if static_dir:
        routes.append(aiohttp.web.static('/', static_dir))

    app = aiohttp.web.Application(middlewares=middlewares)
    app.add_routes(routes)

    if no_cache:
        app.on_response_prepare.append(_no_cache_prepare)

    runner = aiohttp.web.AppRunner(app,
                                   shutdown_timeout=shutdown_timeout)
    await runner.setup()
    server.async_group.spawn(aio.call_on_cancel, runner.cleanup)

    try:
        site = aiohttp.web.TCPSite(runner=runner,
                                   host=host,
                                   port=port,
                                   ssl_context=ssl_ctx,
                                   reuse_address=True)
        await site.start()

    except BaseException:
        await aio.uncancellable(server.async_close())
        raise

    return server


class Server(aio.Resource):
    """Server

    For creating new server see `listen` coroutine.

    When server is closed, all incoming connections are also closed.

    """

    @property
    def async_group(self) -> aio.Group:
        """Async group"""
        return self._async_group

    async def create_connection(self,
                                request: aiohttp.web.Request
                                ) -> 'Connection':
        """Create connection"""
        conn = Connection()

        conn._ws = aiohttp.web.WebSocketResponse()
        await conn._ws.prepare(request)

        conn._remote = _get_remote(request)
        conn._async_group = self.async_group.create_subgroup()
        conn._request_cb = self._request_cb
        conn._autoflush_delay = self._autoflush_delay
        conn._state = self._state or json.Storage()
        conn._parallel_requests = self._parallel_requests
        conn._flush_queue = aio.Queue()

        conn._transport = Transport(ws=conn._ws,
                                    msg_cb=conn._on_msg,
                                    send_queue_size=self._send_queue_size,
                                    max_segment_size=self._max_segment_size,
                                    ping_delay=self._ping_delay,
                                    ping_timeout=self._ping_timeout)

        conn.async_group.spawn(aio.call_on_cancel, conn._transport.async_close)
        conn.async_group.spawn(aio.call_on_done,
                               conn._transport.wait_closing(), conn.close)

        conn.async_group.spawn(conn._sync_loop)

        if self._connection_cb:
            conn.async_group.spawn(aio.call, self._connection_cb, conn)

        return conn

    async def _ws_handler(self, request):
        conn = await self.create_connection(request)

        await conn.wait_closed()

        return conn.ws


class Connection(aio.Resource):
    """Connection

    For creating new connection see `listen` coroutine.

    """

    @property
    def async_group(self) -> aio.Group:
        """Async group"""
        return self._async_group

    @property
    def remote(self) -> str:
        """Remote IP address

        Address is obtained from Forwarded or X-Forwarded-For headers. If
        these headers are not available, socket's remote address is used.

        """
        return self._remote

    @property
    def state(self) -> json.Storage:
        """Server state"""
        return self._state

    @property
    def ws(self) -> aiohttp.web.WebSocketResponse:
        """Associated WebSocket"""
        return self._ws

    async def flush(self):
        """Force synchronization of state data

        Raises:
            ConnectionError

        """
        try:
            flush_future = asyncio.Future()
            self._flush_queue.put_nowait(flush_future)
            await flush_future

        except aio.QueueClosedError:
            raise ConnectionError()

    async def notify(self,
                     name: str,
                     data: json.Data):
        """Send notification

        Raises:
            ConnectionError

        """
        if not self.is_open:
            raise ConnectionError()

        await self._transport.send({'type': 'notify',
                                    'name': name,
                                    'data': data})

    async def _on_msg(self, msg):
        if msg['type'] != 'request':
            raise Exception("invalid message type")

        if self._parallel_requests:
            self.async_group.spawn(self._process_request, msg)

        else:
            await self._process_request(msg)

    async def _process_request(self, req):
        try:
            res = {'type': 'response',
                   'id': req['id']}

            if req['name']:
                try:
                    if not self._request_cb:
                        raise Exception('request handler not implemented')

                    res['data'] = await aio.call(self._request_cb, self,
                                                 req['name'], req['data'])
                    res['success'] = True

                except Exception as e:
                    res['data'] = str(e)
                    res['success'] = False

            else:
                res['data'] = req['data']
                res['success'] = True

            await self._transport.send(res)

        except ConnectionError:
            self.close()

        except Exception as e:
            self.close()
            mlog.error("process request error: %s", e, exc_info=e)

    async def _sync_loop(self):
        flush_future = None
        data = None
        synced_data = None
        data_queue = aio.Queue()

        try:
            with self._state.register_change_cb(data_queue.put_nowait):
                data_queue.put_nowait(self._state.data)

                if not self.is_open:
                    return

                get_data_future = self.async_group.spawn(data_queue.get)
                get_flush_future = self.async_group.spawn(
                    self._flush_queue.get)

                while True:
                    await asyncio.wait([get_data_future, get_flush_future],
                                       return_when=asyncio.FIRST_COMPLETED)

                    if get_flush_future.done():
                        flush_future = get_flush_future.result()
                        get_flush_future = self.async_group.spawn(
                            self._flush_queue.get)

                    else:
                        await asyncio.wait([get_flush_future],
                                           timeout=self._autoflush_delay)

                        if get_flush_future.done():
                            flush_future = get_flush_future.result()
                            get_flush_future = self.async_group.spawn(
                                self._flush_queue.get)

                        else:
                            flush_future = None

                    if get_data_future.done():
                        data = get_data_future.result()
                        get_data_future = self.async_group.spawn(
                            data_queue.get)

                    if self._autoflush_delay != 0:
                        if not data_queue.empty():
                            data = data_queue.get_nowait_until_empty()

                    if synced_data is not data:
                        diff = json.diff(synced_data, data)
                        synced_data = data

                        if diff:
                            await self._transport.send({'type': 'state',
                                                        'diff': diff})

                    if flush_future and not flush_future.done():
                        flush_future.set_result(True)

        except Exception as e:
            mlog.error("sync loop error: %s", e, exc_info=e)

        finally:
            self.close()

            self._flush_queue.close()
            while True:
                if flush_future and not flush_future.done():
                    flush_future.set_exception(ConnectionError())

                if self._flush_queue.empty():
                    break

                flush_future = self._flush_queue.get_nowait()


def _get_remote(request):
    if request.forwarded:
        forwarded_for = request.forwarded[-1].get('for')
        if forwarded_for:
            return forwarded_for

    forwarded_for = request.headers.getall(aiohttp.hdrs.X_FORWARDED_FOR, [])
    if len(forwarded_for) == 1:
        return forwarded_for[0].split(',')[-1].strip()

    return request.remote


async def _no_cache_prepare(request, response):
    response.headers['Cache-Control'] = 'no-cache'
