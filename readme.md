


### Python packages

```
python -m pip install --upgrade aiohttp kubernetes_asyncio click jinja2 numpy pyyaml  
```

Additionally on py3.6:
```
python -m pip install --upgrade dataclasses
```


### Preact import as module

In `hooks.module.js` we change `from 'preact'` to `from './preact.module.js'` so that it matches the actual file name and resolves.
