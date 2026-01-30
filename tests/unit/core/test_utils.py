from core.utils import greet

def test_greet_returns_hello_name():
    assert greet('World') == 'Hello World'
