import click
from core import utils

@click.command()
@click.argument('name', default='World')
def main(name: str) -> None:
    """Simple CLI entrypoint."""
    click.echo(utils.greet(name))

if __name__ == '__main__':
    main()
