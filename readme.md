
# CVLAB Kubernetes Watchdog

A web dashboard for jobs running on EPFL's Kubernetes cluster.
Lists pods per user, the number of GPUs allocated, GPU memory and compute utilization.

The backend is using an async Python HTTP server \texttt{aiohttp} and interfacing with the Kubernetes API.
The frontend web-application uses Preact.


### Python packages to install

```
python -m pip install --upgrade aiohttp kubernetes_asyncio click jinja2 numpy pyyaml
```

Additionally on py3.6:
```
python -m pip install --upgrade dataclasses
```

Since it is mostly pure-Python, we run it on PyPy:
```
conda upgrade pypy3.6
```

### Run server

Specify the port to listen on and the Kubernetes namespace to monitor.

```bash
cd this_repo
python -m kube_watchdog server --namespace cvlab --port 5336 
```


### Preact import as module

In `hooks.module.js` we change `from 'preact'` to `from './preact.module.js'` so that it matches the actual file name and resolves.
