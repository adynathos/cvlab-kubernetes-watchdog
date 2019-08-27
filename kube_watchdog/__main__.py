
import click
from .console import main as console_main
from .web import main as web_main

entrypoint = click.Group(name='kube_watchdog')
entrypoint.add_command(console_main)
entrypoint.add_command(web_main)
if __name__ == '__main__':
	entrypoint()
