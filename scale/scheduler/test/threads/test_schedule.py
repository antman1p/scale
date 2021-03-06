from __future__ import unicode_literals

import django
from django.test import TransactionTestCase
from mock import MagicMock, patch

from job.execution.running.job_exe import RunningJobExecution
from job.execution.running.manager import running_job_mgr
from job.resources import NodeResources
from job.test import utils as job_test_utils
from mesos_api.api import SlaveInfo
from node.test import utils as node_test_utils
from queue.models import Queue
from queue.test import utils as queue_test_utils
from scheduler.models import Scheduler
from scheduler.node.manager import node_mgr
from scheduler.offer.manager import offer_mgr
from scheduler.offer.offer import ResourceOffer
from scheduler.sync.job_type_manager import job_type_mgr
from scheduler.sync.scheduler_manager import scheduler_mgr
from scheduler.threads.schedule import SchedulingThread


class TestSchedulingThread(TransactionTestCase):

    def setUp(self):
        django.setup()

        Scheduler.objects.initialize_scheduler()
        self._driver = MagicMock()

        scheduler_mgr.sync_with_database()
        offer_mgr.clear()

        self.node_agent_1 = 'agent_1'
        self.node_agent_2 = 'agent_2'
        self.slave_infos = [SlaveInfo('host_1', slave_id=self.node_agent_1),
                            SlaveInfo('host_2', slave_id=self.node_agent_2)]
        node_mgr.clear()
        node_mgr.register_agent_ids([self.node_agent_1, self.node_agent_2])
        with patch('scheduler.node.manager.api.get_slaves') as mock_get_slaves:
            mock_get_slaves.return_value = self.slave_infos
            node_mgr.sync_with_database('master_host', 5050)
        # Ignore initial cleanup tasks
        for node in node_mgr.get_nodes():
            node.initial_cleanup_completed()

        self.queue_1 = queue_test_utils.create_queue(cpus_required=4.0, mem_required=1024.0, disk_in_required=100.0,
                                                     disk_out_required=200.0, disk_total_required=300.0)
        self.queue_2 = queue_test_utils.create_queue(cpus_required=8.0, mem_required=512.0, disk_in_required=400.0,
                                                     disk_out_required=45.0, disk_total_required=445.0)
        job_type_mgr.sync_with_database()

        self._scheduling_thread = SchedulingThread(self._driver, '123')

    @patch('mesos_api.tasks.mesos_pb2.TaskInfo')
    def test_successful_schedule(self, mock_taskinfo):
        """Tests successfully scheduling tasks"""
        mock_taskinfo.return_value = MagicMock()

        offer_1 = ResourceOffer('offer_1', self.node_agent_1, NodeResources(cpus=2.0, mem=1024.0, disk=1024.0))
        offer_2 = ResourceOffer('offer_2', self.node_agent_2, NodeResources(cpus=25.0, mem=2048.0, disk=2048.0))
        offer_mgr.add_new_offers([offer_1, offer_2])

        num_tasks = self._scheduling_thread._perform_scheduling()
        self.assertEqual(num_tasks, 2)  # Schedule both queued job executions

    @patch('mesos_api.tasks.mesos_pb2.TaskInfo')
    def test_paused_scheduler(self, mock_taskinfo):
        """Tests running the scheduling thread with a paused scheduler"""
        mock_taskinfo.return_value = MagicMock()

        offer_1 = ResourceOffer('offer_1', self.node_agent_1, NodeResources(cpus=2.0, mem=1024.0, disk=1024.0))
        offer_2 = ResourceOffer('offer_2', self.node_agent_2, NodeResources(cpus=25.0, mem=2048.0, disk=2048.0))
        offer_mgr.add_new_offers([offer_1, offer_2])
        Scheduler.objects.update(is_paused=True)
        scheduler_mgr.sync_with_database()

        num_tasks = self._scheduling_thread._perform_scheduling()
        self.assertEqual(num_tasks, 0)

    @patch('mesos_api.tasks.mesos_pb2.TaskInfo')
    def test_job_type_limit(self, mock_taskinfo):
        """Tests running the scheduling thread with a job type limit"""
        mock_taskinfo.return_value = MagicMock()

        Queue.objects.all().delete()
        job_type_with_limit = job_test_utils.create_job_type()
        job_type_with_limit.max_scheduled = 4
        job_type_with_limit.save()
        job_exe_1 = job_test_utils.create_job_exe(job_type=job_type_with_limit, status='RUNNING')
        queue_test_utils.create_queue(job_type=job_type_with_limit)
        queue_test_utils.create_queue(job_type=job_type_with_limit)
        queue_test_utils.create_queue(job_type=job_type_with_limit)
        queue_test_utils.create_queue(job_type=job_type_with_limit)
        queue_test_utils.create_queue(job_type=job_type_with_limit)
        queue_test_utils.create_queue(job_type=job_type_with_limit)
        job_type_mgr.sync_with_database()
        # One job of this type is already running
        running_job_mgr.add_job_exes([RunningJobExecution(job_exe_1)])

        offer_1 = ResourceOffer('offer_1', self.node_agent_1, NodeResources(cpus=200.0, mem=102400.0, disk=102400.0))
        offer_2 = ResourceOffer('offer_2', self.node_agent_2, NodeResources(cpus=200.0, mem=204800.0, disk=204800.0))
        offer_mgr.add_new_offers([offer_1, offer_2])

        # Ignore cleanup tasks
        for node in node_mgr.get_nodes():
            node.initial_cleanup_completed()

        num_tasks = self._scheduling_thread._perform_scheduling()
        self.assertEqual(num_tasks, 3)  # One is already running, should only be able to schedule 3 more
