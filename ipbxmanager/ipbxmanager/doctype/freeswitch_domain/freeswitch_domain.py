# -*- coding: utf-8 -*-
# Copyright (c) 2018, Nayar Joolfoo and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class FreeswitchDomain(Document):
	def save(self):
		super(FreeswitchDomain, self).save()
		FreeswitchDomain.deploy()	
		
	def on_trash(self):
		import pprint
		pprint.pprint(self)
		for d in self.get_all_children():
			doc = frappe.get_doc(d.doctype,d.name)
			doc.delete()	
		
		#users = frappe.get_all('User', filters={'email': self.sip_email}, fields=['name'])
		sip_groups = frappe.get_all('SIP Group', filters={'freeswitch_domain': self.sip_domain}, fields=['name'])
		pprint.pprint(sip_groups)
		for sip_group in sip_groups:
			sip_group = frappe.get_doc("SIP Group",sip_group.name)
			sip_group.delete()
			
		sip_groups = frappe.get_all('SIP User', filters={'sip_domain': self.sip_domain}, fields=['name'])
		pprint.pprint(sip_groups)
		for sip_group in sip_groups:
			sip_group = frappe.get_doc("SIP User",sip_group.name)
			sip_group.delete()
		FreeswitchDomain.deploy()
	
	def deploy():
		ansible_hosts_file = FreeswitchDomain.ansible_yaml_host_file()
		# TODO: not make absolute
		f=open("/home/frappe/frappe-bench/apps/ipbxmanager/ipbxmanager/ansible/hosts2.yaml","w+")
		f.write(ansible_hosts_file)
		f.close()
		#stats = FreeswitchDomain.run_playbook(
			#playbook_path='/home/frappe/frappe-bench/apps/ipbxmanager/ipbxmanager/ansible/cloudservices.yaml',
			#hosts_path='/home/frappe/frappe-bench/apps/ipbxmanager/ipbxmanager/ansible/hosts2.yaml',
			#key_file = '/home/frappe/.ssh/id_rsa'
		#)
		#print(stats)
		bashCommand = "ansible-playbook -i /home/frappe/frappe-bench/apps/ipbxmanager/ipbxmanager/ansible/hosts2.yaml /home/frappe/frappe-bench/apps/ipbxmanager/ipbxmanager/ansible/cloudservices.yml --tags configuration"
		import subprocess
		process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
		output, error = process.communicate()
		print(output)
		print(error)
		
	def run_playbook(playbook_path, hosts_path, key_file):
		from ansible import playbook, callbacks
		stats = callbacks.AggregateStats()
		playbook_cb = callbacks.PlaybookCallbacks(verbose=0)
		runner_cb = callbacks.PlaybookRunnerCallbacks(stats, verbose=0)
		playbook.PlayBook(
			playbook=playbook_path,
			host_list=hosts_path,
			stats=stats,
			forks=4,
			callbacks=playbook_cb,
			runner_callbacks=runner_cb,
			private_key_file=key_file
			).run()
		return stats
		
	def extra_info(self):
		self.sip_users = frappe.get_all('SIP User', filters={'sip_domain': self.sip_domain})
		self.sip_groups = frappe.get_all('SIP Group', filters={'sip_domain': self.sip_domain})
		self.gsm_lines = frappe.get_all('GSM SIM', filters={'sip_domain': self.sip_domain}, fields=['name','operator','forward_type','forward_to'])
		self.no_sip_users = frappe.db.sql('select count(*) from `tabSIP User` where sip_domain = "%s";' % (self.sip_domain))[0][0]
		self.no_sip_groups = frappe.db.sql('select count(*) from `tabSIP Group` where sip_domain = "%s";' % (self.sip_domain))[0][0]
		#self.gsm_lines = frappe.db.sql('select number,operator,forward_to from `tabGSM SIM` where sip_domain = "%s";' % (self.sip_domain))
		
	def ansible_yaml_host_file():
		import yaml,pprint,re
		
		obj = {
			"freeswitch": {
				"hosts" : {}
			},
			"bind": {
				"hosts": {}
			}			
		}
			
		dns_objs = []

		sip_servers = frappe.get_all('SIP Server')
		for sip_server in sip_servers:
			sip_server = frappe.get_doc('SIP Server',sip_server)
			obj['freeswitch']['hosts'][sip_server.ip] = { "domains" : [] }
			domains = frappe.get_all('Freeswitch Domain',filters={'sip_server': sip_server.name})
			for domain in domains:
				domain_obj = {
					"sip_domain" : domain.name,
					"users" : [],
					"groups" : [],
					"gsm_lines": []
				}
				
				domain = frappe.get_doc('Freeswitch Domain',domain)
				
				users = frappe.get_all('SIP User',filters={'sip_domain': domain.name})
				for user in users:
					user = frappe.get_doc('SIP User',user)
					domain_obj['users'].append({
						"sip_user_id": user.sip_user_id,
						"sip_password": user.sip_password
					})
					
				groups = frappe.get_all('SIP Group',filters={'sip_domain': domain.name})
				for group in groups:
					group = frappe.get_doc('SIP Group',group)
					group_obj = {
						"sip_extension" : group.sip_extension,
						"users" : [],
						"group_name": group.group_name
					}
					for group_user in group.get_all_children():
						pprint.pprint(group_user)
						group_obj['users'].append(re.match("(.*)@.*",group_user.sip_user).group(1))
					domain_obj['groups'].append(group_obj)
				obj['freeswitch']['hosts'][sip_server.ip]['domains'].append(domain_obj)
				
				gsm_lines = frappe.get_all('GSM SIM',filters={'sip_domain': domain.name})
				for gsm_line in gsm_lines:
					gsm_line = frappe.get_doc('GSM SIM',gsm_line)
					forward_to = frappe.get_doc(gsm_line.forward_type, gsm_line.forward_to)
					domain_obj['gsm_lines'].append({
						"number": gsm_line.number,
						"forward_to": 'group/%s@%s' % (forward_to.group_name,domain.name) if gsm_line.forward_type == 'SIP Group' else 'user/%s@%s' % (forward_to.sip_user_id,domain.name),
					})
				
				dns_objs.append({
					'name' : domain.name,
					'a' : sip_server.ip_public if sip_server.ip_public and sip_server.ip_public != '' else sip_server.ip
				})
				
		
		dns_servers = frappe.get_all('DNS Server')
		for dns_server in dns_servers:
			dns_server = frappe.get_doc('DNS Server',dns_server)
			obj['bind']['hosts'][dns_server.ip] = {
				"domains" : dns_objs
			}
		return yaml.dump(obj,default_flow_style=False)
