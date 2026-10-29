import os
import posixpath
from contextlib import contextmanager
from io import BytesIO

import paramiko


@contextmanager
def _connect():
    transport = paramiko.Transport((os.getenv("SFTP_HOST"), int(os.getenv("SFTP_PORT", 22))))
    transport.connect(username=os.getenv("SFTP_USER"), password=os.getenv("SFTP_PASSWORD"))
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        yield sftp
    finally:
        sftp.close()
        transport.close()


def _full_path(path: str) -> str:
    return posixpath.join(os.getenv("SFTP_ROOT"), path.lstrip("/"))


def list_dir(path: str = "") -> list[str]:
    with _connect() as sftp:
        return sftp.listdir(_full_path(path))


def load(path: str) -> BytesIO:
    buffer = BytesIO()
    with _connect() as sftp:
        sftp.getfo(_full_path(path), buffer)
    buffer.seek(0)
    return buffer