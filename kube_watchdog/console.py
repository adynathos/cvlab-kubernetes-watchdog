
import asyncio
import click
import logging
from .monitor import KubernetesPodListSupervisor
from .fairness import pods_calculate_order

log = logging.getLogger(__name__)


@click.command('console')
@click.option('--namespace', type=str, help="Kubernetes namespace to monitor")
@click.option('--config', type=click.Path(exists=True, file_okay=True, dir_okay=False), help="Config file path", default=None)
def main(namespace, config):
	"""
	Display the queue in console.
	"""

	monitor = KubernetesPodListSupervisor(
		namespace = namespace,
		config_file = config,
	)

	def on_kube_state_change(event):
		pod_hierarchy = pods_calculate_order(monitor.get_pods())

		out_lines = [f'\n{"q":<5} {"name":30} {"user":<10} {"prio":<5} {"uo":<5} {"gpu":5}']
		for p in pod_hierarchy:
			prio = p.user_priority if p.user_priority != 0 else 'auto'
			user = p.user or '<anonym>'
			out_lines.append(f'{p.global_ordinal:<5} {p.name:30} {user:<10} {prio:5} {p.user_ordinal:5} {p.num_gpu:5}')

		log.info('\n'.join(out_lines))

	monitor.add_listener(on_kube_state_change)
	asyncio.run(monitor.run())
