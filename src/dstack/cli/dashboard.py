import argparse
import os
from argparse import Namespace

import uvicorn


def dashboard_func(args: Namespace):
    os.environ["DSTACK_HOST"] = args.host
    os.environ["DSTACK_PORT"] = str(args.port)
    uvicorn.run("dstack.dashboard.main:app", host=args.host, port=args.port, reload=True, log_level="error")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("dashboard", help=argparse.SUPPRESS)
    parser.add_argument("--host", metavar="HOST", type=str, help="Bind socket to this host.  Default: 127.0.0.1",
                        default="127.0.0.1")
    parser.add_argument("-p", "--port", metavar="PORT", type=int, help="Bind socket to this port. Default: 8000.",
                        default=8000)
    parser.set_defaults(func=dashboard_func)
