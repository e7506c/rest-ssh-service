import logging
from dataclasses import dataclass

import requests

logging.basicConfig(level=logging.INFO)


@dataclass
class BlackResponse:
    stdin: str = None
    stdout: str = None
    stderr: str = None
    rc: int = -1

    def __str__(self):
        stdout = (self.stdout or "''").replace('\n', '\n ')
        stderr = (self.stderr or "''").replace('\n', '\n ')
        return f'STDIN: {self.stdin}\nSTDOUT: {stdout}\nSTDERR: {stderr}\nRC: {self.rc}\n'


def call_black_service(command: str, ip='localhost', port='4040', headers: dict = None):
    headers = headers or {'ExecutionTimeout': str(5)}
    data = command.encode('utf-8')

    try:
        resp = requests.post(f'http://{ip}:{port}/black_service/', data=data, headers=headers)
        if resp.status_code != requests.codes.ok:
            logging.warning(f'Request to black service failed with status code: {resp.status_code}\n'
                            f'Reason: {resp.reason}\n'
                            f'Body: {resp.text}')
        output = resp.json()
        return BlackResponse(stdin=command,
                             stdout=output.get('out'),
                             stderr=output.get('err'),
                             rc=output.get('rc'))
    except ConnectionError:
        pass


if __name__ == '__main__':
    command_output = call_black_service('pwd')
    logging.info(command_output)

    logging.info(call_black_service('ls'))
