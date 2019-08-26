import logging
from operator import itemgetter
from copy import copy
import sys
import functools

log = logging.getLogger(__name__)

@functools.total_ordering
class LowerIsBetter:
	def __init__(self, value):
		self.value = value

	def __eq__(self, other):
		return self.value < other.value

	def __lt__(self, other):
		# (not (a < b)) means a >= b
		return self.value >= other.value


def sorting_key_within_user(pod_info):
	"""
	Higher key is higher priority
	"""	
	return (
		# is cpu: CPU job is free, always before GPU job
		pod_info.num_gpu == 0, 
		# user priority: # User-set priority, the higher the better
		pod_info.user_priority, 
		# date: older is better
		LowerIsBetter(pod_info.date_started), 
		# Break tie by name
		LowerIsBetter(pod_info.name),
	)


def sorting_key_all_users_together(pod_info):
	"""
	Higher key is higher priority
	"""

	return (
		# is cpu: CPU job is free, always before GPU job
		pod_info.num_gpu == 0,
		# is known user: known user's job before anonymous jobs
		# TODO check list of allowed users instead of any string here
		pod_info.user is not None,
		# position within users queue: lower is better th
		- pod_info.user_ordinal, 
		# date: older is better
		LowerIsBetter(pod_info.date_started), 
		# Break tie by name
		LowerIsBetter(pod_info.name),
	)


def pods_calc_user_queue(pods_of_user : list):
	"""
	Assigns the `user_ordinal` to each pod which has a user
	"""

	pods_of_user.sort(key=sorting_key_within_user, reverse=True)
	
	gpu_accumulation = 0
	
	for pod in pods_of_user:
		gpu_accumulation += pod.num_gpu
		pod.user_ordinal = gpu_accumulation

	return pods_of_user


def pods_calculate_order(pod_infos):
	# only running pods
	pod_infos = [p for p in pod_infos if p.status == 'Running']

	# users' queues
	pods_by_user = {}
	for pod in pod_infos:
		pods_by_user.setdefault(pod.user, []).append(copy(pod))

	pods_all = []
	for user, pods in pods_by_user.items():

		# log.debug(f'{user} - {pods.__len__()} pods')

		# for known users calculate position within queue
		if user is not None:
			pods = pods_calc_user_queue(pods)
		# unknown users: prefer those with fewer gpus
		else:
			for p in pods:
				p.user_ordinal = p.num_gpu
		
		pods_all += pods

	# global order		
	pods_all.sort(key=sorting_key_all_users_together, reverse=True)
		
	# global ordinal
	gpu_accumulation = 0
	for p in pods_all:
		gpu_accumulation += p.num_gpu
		p.global_ordinal = gpu_accumulation

	return pods_all

	# 	print('{gpu_accumulation} {name}	{user}	{user_score}	[{num_gpu} gpus]'.format(**dataclasses.asdict(p))
	
	
	# print('\n'.join(
	# 	'{name} {user} {user_score} [{num_gpu} gpus]'.format(**p)
	# 	for p in pods_all
	# ))
	
