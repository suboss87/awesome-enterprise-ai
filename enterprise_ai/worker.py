"""One request per child, no HTTP listener or retry/fallback behavior."""
import json
import sys
from .common import InputError, loads, obj
from .execution import MAX_WIRE_BYTES
from .__main__ import execute


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_WIRE_BYTES+1)
        if len(raw) > MAX_WIRE_BYTES:
            raise InputError('Request too large')
        request = obj(loads(raw), ['project', 'data', 'mode', 'responses'])
        output = execute(request['project'], request['data'], request['mode'], request['responses'])
        wire = json.dumps({'status': 'succeeded', 'output': output}, allow_nan=False).encode()
        if len(wire) > MAX_WIRE_BYTES:
            raise InputError('Response too large')
        sys.stdout.buffer.write(wire)
    except (InputError, ValueError, TypeError, KeyError, OSError, RecursionError):
        # Do not forward input fragments, provider bodies or environment details.
        print('{"status":"failed"}')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
