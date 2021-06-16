#!/usr/bin/env python3
# TODO: implement restart server
import platform
from argparse import ArgumentParser
from asyncio import TimeoutError, create_subprocess_exec, wait_for
from asyncio.subprocess import PIPE as APIPE
from configparser import ConfigParser
from json import dumps
from logging import basicConfig, getLogger
from os import mkdir
from os.path import isfile, isdir, join
from signal import signal
from subprocess import PIPE as POPIPE
from subprocess import Popen, SubprocessError

from aiohttp import web
from aiohttp.web import Application, Response, run_app
from aiohttp.web_request import Request

WINDOWS = 'windows'
PLATFORM = platform.system().lower()

if PLATFORM != WINDOWS:
    from signal import SIGHUP


class BlackService:
    __INSTANCE_LOGGER_NAME = 'tatlin_black_service_logger'

    def __init__(self, configfile: str):
        self.config = self.Config(configfile)
        if PLATFORM == WINDOWS:
            self.config.server['shell'] = self.config.windows['shell']
            self.config.server['shellkeys'] = self.config.windows['shellkeys']
            self.config.log['log_path'] = self.config.windows['log_path']
        else:
            signal(SIGHUP, self.__signalhandler)
            if not isdir(self.config.log['log_path']):
                mkdir(self.config.log['log_path'])

        basicConfig(level=self.config.log['level'],
                    format=self.config.log['format'],
                    filename=join(self.config.log['log_path'], self.config.log['log_name']))
        self.logger = getLogger(BlackService.__INSTANCE_LOGGER_NAME)
        self.app = Application()
        self.app.add_routes([web.post(self.config.routes['application'], self.__cmdhandler),
                             web.post(self.config.routes['uploadfile'], self.__uploadfilehandler),
                             web.get(self.config.routes['lastresult'], self.__lastcmdhandler),
                             web.get(self.config.routes['status'], self.__statushandler)])
        self.logger.info('config parsed successfully')
        self.logger.info(self.config)
        self.app.on_shutdown.append(self.__shutdown)
        self.last_command = ''
        self.logger.info('started web app')

    class Config:
        def __init__(self, configfile: str):
            self.config = ConfigParser(interpolation=None, allow_no_value=True)
            self.config.read(configfile)
            self.restrictcmds = self.config['server']['restrictcmds'].split('=')
            self.dumps = 'config values:'
            for sect in self.config.sections():
                self.dumps += f'\n {sect}:'
                for opt in self.config.options(sect):
                    self.dumps += f'\n     {opt} {"." * (18 - len(opt))} {self.config.get(sect, opt)}'

        def __str__(self):
            return self.dumps

        @property
        def server(self):
            return self.config['server']

        @property
        def routes(self):
            return self.config['routes']

        @property
        def headers(self):
            return self.config['headers']

        @property
        def log(self):
            return self.config['log']

        @property
        def windows(self):
            return self.config['windows']

    async def __shutdown(self, app) -> None:
        self.logger.info('prepare server to shutdown...')

    def __signalhandler(self, signum, frame) -> None:
        if signum == SIGHUP:
            self.logger.debug('received SIGHUP signal: not implemented yet')

    async def __lastcmdhandler(self, request: Request) -> Response:
        self.logger.debug('request for last command result')
        return Response(status=200, text=self.last_command)

    async def __cmdhandler(self, request: Request) -> Response:
        self.logger.debug('request for command execution')
        if not request.can_read_body:
            self.logger.info('client sent empty request')
            return Response(status=400, text='request has no body')
        try:
            commands = await request.text()
            self.logger.debug(f'accepted commands: "{commands}"')
        except BaseException as e:
            self.logger.info('client sent inconsistent request')
            return Response(status=400, text=f'no commands for me: {e}')
        try:
            shell = self.config.server['shell']
            shellkyes = self.config.server['shellkeys']
            arguments = [arg for arg in (shellkyes, commands) if arg.strip()]

            proc = await create_subprocess_exec(shell, *arguments, stdout=APIPE, stderr=APIPE)

            timeout = request.headers.get(self.config.headers['timeout'], self.config.server['timeout'])

            out, err = await wait_for(proc.communicate(), float(timeout))

            output = dumps({'rc': proc.returncode, 'out': out.decode('utf-8'), 'err': err.decode('utf-8')})
            self.last_command = output
            self.logger.debug(
                f'operation result for commands "{commands}":\n=====================\n{output}\n=====================')
            return Response(status=200, text=output)
        except TimeoutError:
            e = f'commands "{commands}": execution timeout is expired'
            self.logger.info(e)
            return Response(status=400, text=e)
        except RuntimeError as e:
            self.logger.info(str(e))
            return Response(status=500, text=str(e))

    async def __uploadfilehandler(self, request: Request) -> Response:
        self.logger.debug('request for upload file')
        if not request.can_read_body:
            self.logger.warning('client sent empty request')
            return Response(status=400, text='request has no body')
        if not request.headers.get(self.config.headers['uploadfile'], ''):
            self.logger.warning(f'{self.config.headers["uploadfile"]} header is not specified')
            return Response(status=400, text=f'request has no {self.config.headers["uploadfile"]} header')
        data = await request.post()
        if len(data) != 1:
            self.logger.warning('requested none or multiple files for upload')
            return Response(status=400, text='requested none or multiple files for upload')
        try:
            upfile = data[next(iter(data))]
            pathto = request.headers[self.config.headers['uploadfile']]
            self.logger.debug(f'file: "{upfile.filename}" path to upload: "{pathto}"')
            with open(pathto, 'wb') as uf:
                uf.write(upfile.file.read())
        except IOError as e:
            errmsg = f'error while uploading file: {e}'
            self.logger.error(errmsg)
            return Response(status=500, text=errmsg)
        except AttributeError:
            errmsg = 'non-file object requested for upload'
            self.logger.info(errmsg)
            return Response(status=500, text=errmsg)
        infomsg = f'uploaded to "{pathto}"'
        self.logger.debug(infomsg)
        return Response(status=200, text=infomsg)

    async def __statushandler(self, request: Request) -> Response:
        self.logger.debug('request for status info')
        reqstatus = 'echo -n "' \
                    'interface:$(ifconfig | awk \'/%s/ {print $2}\' | cut -d: -f2 2>/dev/null) ' \
                    'hostname:$(hostname) ' \
                    'node:$(awk -F";" \'{print $1}\' /sys/module/dm_ec/cluster/config 2>/dev/null)"' \
                    % request.remote[:request.remote.rfind('.')]
        try:
            with Popen([reqstatus], shell=True, stdout=POPIPE) as stat:
                output = stat.stdout.read().decode()
                ret = 200
        except SubprocessError as err:
            output = err
            ret = 500
            self.logger.warning(f'exception occurred during get status info: "{output}"')
        output = output
        self.logger.debug(f'status info: "{output}"')
        return Response(status=ret, text=output)

    def run(self) -> None:
        run_app(self.app,
                host=self.config.server['iface'],
                port=self.config.server['port'],
                print=None,
                shutdown_timeout=3,
                handle_signals=True,
                reuse_address=True,
                reuse_port=PLATFORM != WINDOWS,  # not supported in Windows
                access_log_format='peer %a: "%r"')
        self.logger.info('the daemon has stopped')


if __name__ == '__main__':
    ap = ArgumentParser(description='BlackService daemon help description')
    ap.add_argument('-d', '--daemon', action='store_true', help='run app as daemon')
    ap.add_argument('-c', '--config', default='tatlin-black-service.ini', help='config file path to')
    args = ap.parse_args()
    if isfile(args.config) and args.daemon:
        BlackService(args.config).run()
    else:
        ap.print_help()
