import pytest
from mannux.cli import create_parser, handle_cli_commands

def test_cli_parser_defaults():
    parser = create_parser()
    args = parser.parse_args([])
    assert args.verbose is False
    assert args.debug is False
    assert args.status is False
    assert args.json is False
    assert args.inhibit_toggle is False

def test_cli_parser_flags():
    parser = create_parser()
    args = parser.parse_args(["--status", "--json", "-v"])
    assert args.status is True
    assert args.json is True
    assert args.verbose is True
