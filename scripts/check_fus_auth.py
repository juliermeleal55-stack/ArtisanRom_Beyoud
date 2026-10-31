#!/usr/bin/env python3
"""Regression test for the pinned public FUS protocol implementation, not device credentials."""
import argparse

# Synthetic 16-byte nonce encrypted by the public protocol-v2 implementation.
# This is a deterministic test vector, not a server nonce or device identifier.
ENCRYPTED_NONCE = 'NGMM/CsB7uQG/Q7rdosp0rQ+m7isk2pEm5AWIu4WFWk='
PLAINTEXT_NONCE = '0123456789abcdef'


def verify(auth):
    nonce = auth.decryptnonce(ENCRYPTED_NONCE)
    if nonce != PLAINTEXT_NONCE:
        raise ValueError('Installed samloader uses an incompatible FUS nonce implementation')
    if not auth.getauth(nonce):
        raise ValueError('FUS signature calculation returned an empty result')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Also request a nonce from FUS; no firmware or IMEI is sent')
    args = parser.parse_args()
    from samloader import auth
    verify(auth)
    print('FUS synthetic nonce regression: passed')
    if args.live:
        from samloader.fusclient import FUSClient
        client = FUSClient()
        if len(getattr(client, 'nonce', '')) < 16:
            raise ValueError('FUS returned an unusable nonce; firmware download cannot proceed')
        print('FUS live authentication initialization: passed (no device identifier sent)')


if __name__ == '__main__':
    main()
