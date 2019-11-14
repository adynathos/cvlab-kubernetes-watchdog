"use strict";
import { h, render } from './lib/preact-10.0.5/preact.module.js';
import { useState, useEffect } from './lib/preact-10.0.5/hooks.module.js';
// import { h, render } from './lib/preact-10.0.0.rc1/preact.module.js';
// import { useState, useEffect } from './lib/preact-10.0.0.rc1/hooks.module.js';

const UPDATE_INTERVAL = 1.5;

const ORDINAL_ENDING = ['th', 'st', 'nd', 'rd', 'th', 'th', 'th', 'th', 'th', 'th'];
function ordinal_text(num) {
	if (num === 0) {
		return "CPU";
	}
	return num.toString() + ORDINAL_ENDING[num % 10];
}

function ordinal_class(ordinal) {
	return ordinal <= 6 ? `ord-${ordinal}` : 'ord-6';
}

function UtilizationBar(attrs) {
	const percent = `${Math.round(attrs.value*100)}%`;
	const sty = {'width': percent};
	const message = `${attrs.title}: ${percent}`;

	return h('div', {'class': 'utilization-box', 'title': message}, [
		h('div', {'class': `utilization-bar ${attrs.variant}`, 'title': message, 'style': sty}),
	])
}

const MSG_GPU_MEM = 'GPU memory allocated';
const MSG_GPU_COMPUTE = 'GPU compute utilization';

function GpuUtilizationCell(attrs) {
	const pod_info = attrs.pod_info;

	const num_gpu = h('span', {}, pod_info.num_gpu === 0 ? "CPU" : pod_info.num_gpu.toString());

	const elems = [num_gpu];
	// ${pod_info.utilization_mem}  ${pod_info.utilization_compute}
	if(pod_info.utilization_mem !== null) {
		elems.push(
			' ',
			h(UtilizationBar, {
				'title': MSG_GPU_MEM,
				'value': pod_info.utilization_mem,
				'variant': 'mem',
			}),
			' ',
			h(UtilizationBar, {
				'title': MSG_GPU_COMPUTE,
				'value': pod_info.utilization_compute,
				'variant': 'compute',
			}),
		);
	}

	return h('td', {'class': 'gpu'}, elems);
}


function JobListRow(attrs) {
	const pod_info = attrs.pod_info;

	const known_user = pod_info.user !== null;

	const [prio_class, prio_text] = pod_info.user_priority === 0 ? 
		["priority auto", "auto"] : (
			pod_info.user_priority < 0 ? 
				["priority low", pod_info.user_priority.toString()] :
				["priority high", `+${pod_info.user_priority}`]
		);

	const ord_cls = ordinal_class(pod_info.user_ordinal);

	return h('tr', 
		{'class': 'job-row'},
		[
			// name
			h('td', {'class': 'name'}, 
				h('a', {'href': `describe/${pod_info.name}`, 'target': '_blank'}, pod_info.name),
			),
			// owner
			(known_user ? 
				h('td', {'class': 'user'},  pod_info.user) :
				h('td', {'class': 'user anonymous'},  "anonymous" )
			),
			// gpu
			h(GpuUtilizationCell, {'pod_info': attrs.pod_info}),
			// user priority
			h('td', {'class': prio_class}, prio_text),
			// user ordinal
			h('td', {'class': `user-ord ${ord_cls}`}, known_user ? ordinal_text(pod_info.user_ordinal) : []),
		],
	);
}

const job_list_header = h('thead', {}, [
	h('tr', {}, [
		h('th', {'class': 'name'}, "Job Name"),
		h('th', {'class': 'user'}, "User"),
		h('th', {'class': 'gpu'}, [
			"GPUs ",
			h('img', {'src': 'static/images/utilization_mem.svg', 'title': MSG_GPU_MEM}),
			" ",
			h('img', {'src': 'static/images/utilization_compute.svg', 'title': MSG_GPU_COMPUTE}),
		]),
		h('th', {'class': 'priority'}, "Priority"),
		h('th', {'class': 'user-ord'}, "User's GPU"),
	]),
]);

function JobRowSeparator(attrs) {
	const ordinal = attrs.ordinal;

	const text = ordinal_text(ordinal);
	const cls = ordinal_class(ordinal);

	return h('tr', {}, 
		h('td', {'class': `separator ${cls}`, 'colspan': 5}, text),
	);
}

function JobList() {
	const [pod_list, set_pod_list] = useState([]);

	useEffect(() => {

		const check_for_update = async () => {
			const response_raw = await fetch('api/state');
			const response = await response_raw.json();

			set_pod_list(response);
		};

		check_for_update();

		const timer_handle = setInterval(check_for_update, UPDATE_INTERVAL * 1000);

		console.log('Registered update timer', timer_handle);

		// return cleanup function
		return () => {
			clearInterval(timer_handle);
			console.log('Quit update timer', timer_handle);
		}
	}, 
	[], // empty dependency list means this is not invalidated on component updates
	);

	const rows = [];
	let prev_ord = null;

	for(const pod_info of pod_list) {
		// anonymous jobs do not have a valid user_ordinal
		const known_user = pod_info.user !== null;
		const this_ord = known_user ? pod_info.user_ordinal : null;

		if (prev_ord !== null && prev_ord !== this_ord) {
			rows.push(h(JobRowSeparator, 
				{'ordinal': prev_ord, 'key': `sep_ord_${prev_ord}`},
			));
		}

		rows.push(h(JobListRow, 
			{'pod_info': pod_info, 'key': pod_info.name},
		));

		prev_ord = this_ord;
	}
	
	// if the last job is not anonymous, add the last separator as summary to how many gpus were used
	if (prev_ord !== null) {
		rows.push(h(JobRowSeparator, 
			{'ordinal': prev_ord, 'key': `sep_ord_${prev_ord}`},
		));
	}

	return h('table', {'id': 'job-list'}, [
		job_list_header,
		h('tbody', {}, rows),
	]);
}

const DOM_loaded_promise = new Promise((accept, reject) => {
	if (document.readyState === 'loading') {  // Loading hasn't finished yet
		 document.addEventListener('DOMContentLoaded', accept);
	} else {  // `DOMContentLoaded` has already fired
		accept();
	}
}); 

DOM_loaded_promise.then(() => {
	render(
		h(JobList),
		document.getElementById('job-list-container'),
	);
});

