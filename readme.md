


### Python packages to install

```
python -m pip install --upgrade aiohttp kubernetes_asyncio click jinja2 numpy pyyaml  
```

Additionally on py3.6:
```
python -m pip install --upgrade dataclasses
```

### Run server

Specify the port to listen on and the Kubernetes namespace to monitor.

```bash
cd this_repo
python -m kube_watchdog --port 5336 --namespace cvlab
```


### Preact import as module

In `hooks.module.js` we change `from 'preact'` to `from './preact.module.js'` so that it matches the actual file name and resolves.
