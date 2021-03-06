from __future__ import unicode_literals

import django
from django.db import transaction
from django.test import TransactionTestCase
from mock import patch

import job.test.utils as job_test_utils
import recipe.test.utils as recipe_test_utils
import storage.test.utils as storage_test_utils
import trigger.test.utils as trigger_test_utils
from job.configuration.interface.job_interface import JobInterface
from job.models import Job, JobType, JobTypeRevision
from recipe.configuration.data.exceptions import InvalidRecipeConnection
from recipe.configuration.data.recipe_data import RecipeData
from recipe.configuration.definition.exceptions import InvalidDefinition
from recipe.configuration.definition.recipe_definition import RecipeDefinition
from recipe.exceptions import ReprocessError
from recipe.handlers.graph_delta import RecipeGraphDelta
from recipe.models import Recipe, RecipeFile, RecipeJob, RecipeType, RecipeTypeRevision
from trigger.models import TriggerRule


class TestJobTypeManagerEditJobType(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.workspace = storage_test_utils.create_workspace()

        interface = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.job_interface = JobInterface(interface)
        self.job_type = JobType.objects.create_job_type('name', '1.0', self.job_interface)

        new_valid_interface = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['application/json'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.new_valid_job_interface = JobInterface(new_valid_interface)

        new_invalid_interface = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 2',
                'type': 'files',
                'media_types': ['image/png', 'image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 2',
                'type': 'file',
            }]}
        self.new_invalid_job_interface = JobInterface(new_invalid_interface)

        self.definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type.name,
                    'version': self.job_type.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }]
        }
        self.recipe_def = RecipeDefinition(self.definition)
        self.recipe = RecipeType.objects.create_recipe_type('name', '1.0', 'title', 'description', self.recipe_def,
                                                            None)

    def test_valid_interface(self):
        """Tests calling JobTypeManager.edit_job_type() where the job type is in a recipe and a valid interface change
        is made"""

        # Call test
        JobType.objects.edit_job_type(self.job_type.id, self.new_valid_job_interface)

        # Check results
        job_type = JobType.objects.get(pk=self.job_type.id)
        self.assertDictEqual(job_type.get_job_interface().get_dict(), self.new_valid_job_interface.get_dict())
        self.assertEqual(job_type.revision_num, 2)
        # New revision due to interface change
        num_of_revs = JobTypeRevision.objects.filter(job_type_id=job_type.id).count()
        self.assertEqual(num_of_revs, 2)

    def test_invalid_interface(self):
        """Tests calling JobTypeManager.edit_job_type() where the job type is in a recipe and an invalid interface
        change is made"""

        # Call test
        self.assertRaises(InvalidDefinition, JobType.objects.edit_job_type, self.job_type.id,
                          self.new_invalid_job_interface)

        # Check results
        job_type = JobType.objects.get(pk=self.job_type.id)
        self.assertDictEqual(job_type.get_job_interface().get_dict(), self.job_interface.get_dict())
        self.assertEqual(job_type.revision_num, 1)
        num_of_revs = JobTypeRevision.objects.filter(job_type_id=job_type.id).count()
        self.assertEqual(num_of_revs, 1)


class TestJobTypeManagerValidateJobType(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.workspace = storage_test_utils.create_workspace()

        interface = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.job_interface = JobInterface(interface)
        self.job_type = JobType.objects.create_job_type('name', '1.0', self.job_interface)

        new_valid_interface = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['application/json'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.new_valid_job_interface = JobInterface(new_valid_interface)

        new_invalid_interface = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 2',
                'type': 'files',
                'media_types': ['image/png', 'image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 2',
                'type': 'file',
            }]}
        self.new_invalid_job_interface = JobInterface(new_invalid_interface)

        self.definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type.name,
                    'version': self.job_type.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }]
        }
        self.recipe_def = RecipeDefinition(self.definition)
        self.recipe = RecipeType.objects.create_recipe_type('name', '1.0', 'title', 'description', self.recipe_def,
                                                            None)

    def test_valid_interface(self):
        """Tests calling JobTypeManager.validate_job_type() where the job type is in a recipe and a valid interface
        change is made"""

        # Call test
        warnings = JobType.objects.validate_job_type(self.job_type.name, self.job_type.version,
                                                     self.new_valid_job_interface)

        # Check results
        job_type = JobType.objects.get(pk=self.job_type.id)
        self.assertDictEqual(job_type.get_job_interface().get_dict(), self.job_interface.get_dict())
        self.assertEqual(job_type.revision_num, 1)
        num_of_revs = JobTypeRevision.objects.filter(job_type_id=job_type.id).count()
        self.assertEqual(num_of_revs, 1)
        self.assertEqual(len(warnings), 1)

    def test_invalid_interface(self):
        """Tests calling JobTypeManager.validate_job_type() where the job type is in a recipe and an invalid interface
        change is made"""

        # Call test
        self.assertRaises(InvalidDefinition, JobType.objects.validate_job_type, self.job_type.name,
                          self.job_type.version, self.new_invalid_job_interface)

        # Check results
        job_type = JobType.objects.get(pk=self.job_type.id)
        self.assertDictEqual(job_type.get_job_interface().get_dict(), self.job_interface.get_dict())
        self.assertEqual(job_type.revision_num, 1)
        num_of_revs = JobTypeRevision.objects.filter(job_type_id=job_type.id).count()
        self.assertEqual(num_of_revs, 1)


class TestRecipeManager(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.standalone_job = job_test_utils.create_job(status='RUNNING')

        job_type_a_1 = job_test_utils.create_job_type()
        job_type_a_2 = job_test_utils.create_job_type()
        definition_a = {
            'version': '1.0',
            'input_data': [],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': job_type_a_1.name,
                    'version': job_type_a_1.version,
                }
            }, {
                'name': 'Job 2',
                'job_type': {
                    'name': job_type_a_2.name,
                    'version': job_type_a_2.version,
                },
                'dependencies': [{
                    'name': 'Job 1'
                }],
            }],
        }
        recipe_type_a = recipe_test_utils.create_recipe_type(definition=definition_a)
        self.job_a_1 = job_test_utils.create_job(job_type=job_type_a_1, status='FAILED', num_exes=1)
        self.job_a_2 = job_test_utils.create_job(job_type=job_type_a_2, status='BLOCKED')
        data_a = {
            'version': '1.0',
            'input_data': [],
            'workspace_id': 1,
        }
        self.recipe_a = recipe_test_utils.create_recipe(recipe_type=recipe_type_a, data=data_a)
        recipe_test_utils.create_recipe_job(recipe=self.recipe_a, job_name='Job 1', job=self.job_a_1)
        recipe_test_utils.create_recipe_job(recipe=self.recipe_a, job_name='Job 2', job=self.job_a_2)

        # Create recipe for re-queing a job that should now be BLOCKED (and its dependencies)
        job_type_b_1 = job_test_utils.create_job_type()
        job_type_b_2 = job_test_utils.create_job_type()
        job_type_b_3 = job_test_utils.create_job_type()
        definition_b = {
            'version': '1.0',
            'input_data': [],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': job_type_b_1.name,
                    'version': job_type_b_1.version,
                }
            }, {
                'name': 'Job 2',
                'job_type': {
                    'name': job_type_b_2.name,
                    'version': job_type_b_2.version,
                },
                'dependencies': [{
                    'name': 'Job 1'
                }],
            }, {
                'name': 'Job 3',
                'job_type': {
                    'name': job_type_b_3.name,
                    'version': job_type_b_3.version,
                },
                'dependencies': [{
                    'name': 'Job 2'
                }],
            }],
        }
        recipe_type_b = recipe_test_utils.create_recipe_type(definition=definition_b)
        self.job_b_1 = job_test_utils.create_job(job_type=job_type_b_1, status='FAILED')
        self.job_b_2 = job_test_utils.create_job(job_type=job_type_b_2, status='CANCELED')
        self.job_b_3 = job_test_utils.create_job(job_type=job_type_b_3, status='BLOCKED')
        data_b = {
            'version': '1.0',
            'input_data': [],
            'workspace_id': 1,
        }
        self.recipe_b = recipe_test_utils.create_recipe(recipe_type=recipe_type_b, data=data_b)
        recipe_test_utils.create_recipe_job(recipe=self.recipe_b, job_name='Job 1', job=self.job_b_1)
        recipe_test_utils.create_recipe_job(recipe=self.recipe_b, job_name='Job 2', job=self.job_b_2)
        recipe_test_utils.create_recipe_job(recipe=self.recipe_b, job_name='Job 3', job=self.job_b_3)

        self.job_ids = [self.standalone_job.id, self.job_a_1.id, self.job_b_2.id]
        self.dependent_job_ids = {self.job_a_2.id, self.job_b_3.id}

    @patch('recipe.models.Job.objects.lock_jobs')
    def test_get_recipe_handlers_for_jobs(self, mock_lock_jobs):
        """Tests calling RecipeManager.get_recipe_handlers_for_jobs() successfully"""

        handlers = Recipe.objects.get_recipe_handlers_for_jobs(self.job_ids)

        mock_lock_jobs.assert_called_with(self.dependent_job_ids)
        self.assertEqual(len(handlers), 2)
        recipe_ids = set()
        for handler in handlers:
            recipe_ids.add(handler.recipe.id)
        self.assertSetEqual(recipe_ids, {self.recipe_a.id, self.recipe_b.id})


class TestRecipeManagerCreateRecipe(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.workspace = storage_test_utils.create_workspace()

        self.file = storage_test_utils.create_file()

        interface_1 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.job_type_1 = job_test_utils.create_job_type(interface=interface_1)

        interface_2 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 2',
                'type': 'files',
                'media_types': ['image/png', 'image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 2',
                'type': 'file',
            }]}
        self.job_type_2 = job_test_utils.create_job_type(interface=interface_2)

        definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type_1.name,
                    'version': self.job_type_1.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }, {
                'name': 'Job 2',
                'job_type': {
                    'name': self.job_type_2.name,
                    'version': self.job_type_2.version,
                },
                'dependencies': [{
                    'name': 'Job 1',
                    'connections': [{
                        'output': 'Test Output 1',
                        'input': 'Test Input 2',
                    }]
                }]
            }]
        }
        RecipeDefinition(definition).validate_job_interfaces()
        self.recipe_type = recipe_test_utils.create_recipe_type(definition=definition)

        self.data = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'file_id': self.file.id,
            }],
            'workspace_id': self.workspace.id,
        }

    def test_successful(self):
        """Tests calling RecipeManager.create_recipe() successfully."""

        event = trigger_test_utils.create_trigger_event()
        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data), event=event)

        # Make sure the recipe jobs get created with the correct job types
        recipe_job_1 = RecipeJob.objects.get(recipe_id=handler.recipe.id, job_name='Job 1')
        recipe_job_2 = RecipeJob.objects.get(recipe_id=handler.recipe.id, job_name='Job 2')
        self.assertEqual(recipe_job_1.job.job_type.id, self.job_type_1.id)
        self.assertEqual(recipe_job_2.job.job_type.id, self.job_type_2.id)

        # Make sure the recipe jobs get created in the correct order
        self.assertLess(recipe_job_1.job_id, recipe_job_2.job_id)

        recipe_files = RecipeFile.objects.filter(recipe=handler.recipe)
        self.assertEqual(len(recipe_files), 1)
        self.assertEqual(recipe_files[0].scale_file_id, self.file.id)

    def test_successful_supersede_same_recipe_type(self):
        """Tests calling RecipeManager.create_recipe() to supersede a recipe with the same recipe type."""

        event = trigger_test_utils.create_trigger_event()
        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data), event=event)
        recipe = Recipe.objects.get(id=handler.recipe.id)
        recipe_job_1 = RecipeJob.objects.select_related('job').get(recipe_id=handler.recipe.id, job_name='Job 1')
        recipe_job_2 = RecipeJob.objects.select_related('job').get(recipe_id=handler.recipe.id, job_name='Job 2')
        superseded_jobs = {'Job 1': recipe_job_1.job, 'Job 2': recipe_job_2.job}

        # Create a new recipe of the same type where we want to reprocess Job 2
        graph = self.recipe_type.get_recipe_definition().get_graph()
        delta = RecipeGraphDelta(graph, graph)
        delta.reprocess_identical_node('Job 2')  # We want to reprocess Job 2
        new_handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=None, event=event,
                                                   superseded_recipe=recipe, delta=delta,
                                                   superseded_jobs=superseded_jobs)

        # Check that old recipe and job 2 are superseded, job 1 should be copied (not superseded)
        recipe = Recipe.objects.get(id=recipe.id)
        job_1 = Job.objects.get(id=recipe_job_1.job_id)
        job_2 = Job.objects.get(id=recipe_job_2.job_id)
        self.assertTrue(recipe.is_superseded)
        self.assertFalse(job_1.is_superseded)
        self.assertTrue(job_2.is_superseded)

        # Check that new recipe supersedes the old one, job 1 is copied from old recipe, and job 2 supersedes old job 2
        new_recipe = Recipe.objects.get(id=new_handler.recipe.id)
        new_recipe_job_1 = RecipeJob.objects.select_related('job').get(recipe_id=new_handler.recipe.id,
                                                                       job_name='Job 1')
        new_recipe_job_2 = RecipeJob.objects.select_related('job').get(recipe_id=new_handler.recipe.id,
                                                                       job_name='Job 2')
        self.assertEqual(new_recipe.superseded_recipe_id, recipe.id)
        self.assertEqual(new_recipe.root_superseded_recipe_id, recipe.id)
        self.assertDictEqual(new_recipe.data, recipe.data)
        self.assertEqual(new_recipe_job_1.job.id, job_1.id)
        self.assertFalse(new_recipe_job_1.is_original)
        self.assertIsNone(new_recipe_job_1.job.superseded_job)
        self.assertIsNone(new_recipe_job_1.job.root_superseded_job)
        self.assertNotEqual(new_recipe_job_2.job.id, job_2.id)
        self.assertTrue(new_recipe_job_2.is_original)
        self.assertEqual(new_recipe_job_2.job.superseded_job_id, job_2.id)
        self.assertEqual(new_recipe_job_2.job.root_superseded_job_id, job_2.id)

    def test_successful_supersede_different_recipe_type(self):
        """Tests calling RecipeManager.create_recipe() to supersede a recipe with a different recipe type version that
        has one identical node, and deletes another node to replace it with a new one.
        """

        interface_3 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 3',
                'type': 'files',
                'media_types': ['image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 3',
                'type': 'file',
            }]}
        job_type_3 = job_test_utils.create_job_type(interface=interface_3)
        new_definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type_1.name,
                    'version': self.job_type_1.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }, {
                'name': 'Job 3',
                'job_type': {
                    'name': job_type_3.name,
                    'version': job_type_3.version,
                },
                'dependencies': [{
                    'name': 'Job 1',
                    'connections': [{
                        'output': 'Test Output 1',
                        'input': 'Test Input 3',
                    }]
                }]
            }]
        }
        new_recipe_type = recipe_test_utils.create_recipe_type(name=self.recipe_type.name, definition=new_definition)

        event = trigger_test_utils.create_trigger_event()
        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data), event=event)
        recipe = Recipe.objects.get(id=handler.recipe.id)
        recipe_job_1 = RecipeJob.objects.select_related('job').get(recipe_id=handler.recipe.id, job_name='Job 1')
        recipe_job_2 = RecipeJob.objects.select_related('job').get(recipe_id=handler.recipe.id, job_name='Job 2')
        job_exe_2 = job_test_utils.create_job_exe(job=recipe_job_2.job)
        try:
            from product.models import ProductFile
            from product.test import utils as product_test_utils
            product = product_test_utils.create_product(job_exe=job_exe_2, has_been_published=True, is_published=True)
        except ImportError:
            product = None
        superseded_jobs = {'Job 1': recipe_job_1.job, 'Job 2': recipe_job_2.job}

        # Create a new recipe with a different version
        graph_a = self.recipe_type.get_recipe_definition().get_graph()
        graph_b = new_recipe_type.get_recipe_definition().get_graph()
        delta = RecipeGraphDelta(graph_a, graph_b)
        new_handler = Recipe.objects.create_recipe(recipe_type=new_recipe_type, data=None, event=event,
                                                   superseded_recipe=recipe, delta=delta,
                                                   superseded_jobs=superseded_jobs)

        # Check that old recipe and job 2 are superseded, job 1 should be copied (not superseded)
        recipe = Recipe.objects.get(id=recipe.id)
        job_1 = Job.objects.get(id=recipe_job_1.job_id)
        job_2 = Job.objects.get(id=recipe_job_2.job_id)
        self.assertTrue(recipe.is_superseded)
        self.assertFalse(job_1.is_superseded)
        self.assertTrue(job_2.is_superseded)

        # Check that product of job 2 (which was superseded with no new job) was unpublished
        if product:
            product = ProductFile.objects.get(id=product.id)
            self.assertFalse(product.is_published)
            self.assertIsNotNone(product.unpublished)

        # Check that new recipe supersedes the old one, job 1 is copied from old recipe, and job 2 is new and does not
        # supersede anything
        new_recipe = Recipe.objects.get(id=new_handler.recipe.id)
        new_recipe_job_1 = RecipeJob.objects.select_related('job').get(recipe_id=new_handler.recipe.id,
                                                                       job_name='Job 1')
        new_recipe_job_2 = RecipeJob.objects.select_related('job').get(recipe_id=new_handler.recipe.id,
                                                                       job_name='Job 3')
        self.assertEqual(new_recipe.superseded_recipe_id, recipe.id)
        self.assertEqual(new_recipe.root_superseded_recipe_id, recipe.id)
        self.assertDictEqual(new_recipe.data, recipe.data)
        self.assertEqual(new_recipe_job_1.job.id, job_1.id)
        self.assertFalse(new_recipe_job_1.is_original)
        self.assertIsNone(new_recipe_job_1.job.superseded_job)
        self.assertIsNone(new_recipe_job_1.job.root_superseded_job)
        self.assertNotEqual(new_recipe_job_2.job.id, job_2.id)
        self.assertTrue(new_recipe_job_2.is_original)
        self.assertIsNone(new_recipe_job_2.job.superseded_job_id)
        self.assertIsNone(new_recipe_job_2.job.root_superseded_job_id)


class TestRecipeManagerReprocessRecipe(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.workspace = storage_test_utils.create_workspace()

        self.file = storage_test_utils.create_file()

        configuration = {
            'version': '1.0',
            'condition': {
                'media_type': 'text/plain',
            },
            'data': {
                'input_data_name': 'Recipe Input',
                'workspace_name': self.workspace.name,
            }
        }
        self.rule = trigger_test_utils.create_trigger_rule(configuration=configuration)
        self.event = trigger_test_utils.create_trigger_event(rule=self.rule)

        interface_1 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.job_type_1 = job_test_utils.create_job_type(interface=interface_1)

        interface_2 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 2',
                'type': 'files',
                'media_types': ['image/png', 'image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 2',
                'type': 'file',
            }]}
        self.job_type_2 = job_test_utils.create_job_type(interface=interface_2)

        definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type_1.name,
                    'version': self.job_type_1.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }, {
                'name': 'Job 2',
                'job_type': {
                    'name': self.job_type_2.name,
                    'version': self.job_type_2.version,
                },
                'dependencies': [{
                    'name': 'Job 1',
                    'connections': [{
                        'output': 'Test Output 1',
                        'input': 'Test Input 2',
                    }]
                }]
            }]
        }
        RecipeDefinition(definition).validate_job_interfaces()
        self.recipe_type = recipe_test_utils.create_recipe_type(definition=definition, trigger_rule=self.rule)

        self.data = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'file_id': self.file.id,
            }],
            'workspace_id': self.workspace.id,
        }

    def test_forced_all_job(self):
        """Tests reprocessing a recipe without any changes by forcing all jobs."""

        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data),
                                               event=self.event)

        new_handler = Recipe.objects.reprocess_recipe(handler.recipe.id, all_jobs=True)

        # Make sure the recipe jobs get created with the correct job types
        recipe_job_1 = RecipeJob.objects.get(recipe_id=new_handler.recipe.id, job_name='Job 1')
        recipe_job_2 = RecipeJob.objects.get(recipe_id=new_handler.recipe.id, job_name='Job 2')
        self.assertEqual(recipe_job_1.job.job_type.id, self.job_type_1.id)
        self.assertEqual(recipe_job_2.job.job_type.id, self.job_type_2.id)
        self.assertEqual(recipe_job_1.job.status, 'QUEUED')
        self.assertEqual(recipe_job_2.job.status, 'PENDING')

    def test_forced_specific_job(self):
        """Tests reprocessing a recipe without any changes by forcing a single job."""

        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data),
                                               event=self.event)

        new_handler = Recipe.objects.reprocess_recipe(handler.recipe.id, ['Job 1'])

        # Make sure the recipe jobs get created with the correct job types
        recipe_job_1 = RecipeJob.objects.get(recipe_id=new_handler.recipe.id, job_name='Job 1')
        self.assertEqual(recipe_job_1.job.job_type.id, self.job_type_1.id)
        self.assertEqual(recipe_job_1.job.status, 'QUEUED')

    def test_priority(self):
        """Tests reprocessing a recipe with a job priority override."""

        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data),
                                               event=self.event)

        new_handler = Recipe.objects.reprocess_recipe(handler.recipe.id, all_jobs=True, priority=1111)

        # Make sure the recipe jobs get created with the correct job types
        recipe_job_1 = RecipeJob.objects.get(recipe_id=new_handler.recipe.id, job_name='Job 1')
        self.assertEqual(recipe_job_1.job.job_type.id, self.job_type_1.id)
        self.assertEqual(recipe_job_1.job.status, 'QUEUED')
        self.assertEqual(recipe_job_1.job.priority, 1111)

    def test_no_changes(self):
        """Tests reprocessing a recipe that has not changed without specifying any jobs throws an error."""

        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data),
                                               event=self.event)

        self.assertRaises(ReprocessError, Recipe.objects.reprocess_recipe, handler.recipe.id)

    def test_different_recipe_type(self):
        """Tests reprocessing a recipe that was updated to a new revision since it originally ran."""

        interface_3 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 3',
                'type': 'files',
                'media_types': ['image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 3',
                'type': 'file',
            }]}
        job_type_3 = job_test_utils.create_job_type(interface=interface_3)
        new_definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type_1.name,
                    'version': self.job_type_1.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }, {
                'name': 'Job 3',
                'job_type': {
                    'name': job_type_3.name,
                    'version': job_type_3.version,
                },
                'dependencies': [{
                    'name': 'Job 1',
                    'connections': [{
                        'output': 'Test Output 1',
                        'input': 'Test Input 3',
                    }]
                }]
            }]
        }

        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data),
                                               event=self.event)
        recipe = Recipe.objects.get(id=handler.recipe.id)
        recipe_test_utils.edit_recipe_type(self.recipe_type, new_definition)

        new_handler = Recipe.objects.reprocess_recipe(recipe.id)

        # Make sure the recipe jobs get created with the correct job types
        recipe_job_1 = RecipeJob.objects.get(recipe_id=new_handler.recipe.id, job_name='Job 1')
        recipe_job_3 = RecipeJob.objects.get(recipe_id=new_handler.recipe.id, job_name='Job 3')
        self.assertEqual(recipe_job_1.job.job_type.id, self.job_type_1.id)
        self.assertEqual(recipe_job_3.job.job_type.id, job_type_3.id)
        self.assertEqual(recipe_job_1.job.status, 'QUEUED')
        self.assertEqual(recipe_job_3.job.status, 'PENDING')

    def test_reprocess_superseded_recipe(self):
        """Tests reprocessing a recipe that is already superseded throws an error."""

        handler = Recipe.objects.create_recipe(recipe_type=self.recipe_type, data=RecipeData(self.data),
                                               event=self.event)

        handler.recipe.is_superseded = True
        handler.recipe.save()

        self.assertRaises(ReprocessError, Recipe.objects.reprocess_recipe, handler.recipe.id, all_jobs=True)


class TestRecipePopulateJobs(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.recipe = recipe_test_utils.create_recipe()
        self.recipe_job1 = recipe_test_utils.create_recipe_job(self.recipe, job_name='job 1')
        self.recipe_job2 = recipe_test_utils.create_recipe_job(self.recipe, job_name='job 2')
        self.recipe_job3 = recipe_test_utils.create_recipe_job(self.recipe, job_name='job 3')

    def test_successful(self):
        """Tests calling ProductFileManager.populate_source_ancestors() successfully"""

        recipe = Recipe.objects.get_details(self.recipe.id)
        jobs = list(recipe.jobs)
        self.assertEqual(len(jobs), 3)
        self.assertTrue(jobs[0].job_name in ['job 1', 'job 2', 'job 3'])
        self.assertTrue(jobs[0].job_name in ['job 1', 'job 2', 'job 3'])
        self.assertTrue(jobs[0].job_name in ['job 1', 'job 2', 'job 3'])


class TestRecipeTypeManagerCreateRecipeType(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.workspace = storage_test_utils.create_workspace()

        interface_1 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.job_type_1 = job_test_utils.create_job_type(interface=interface_1)

        interface_2 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 2',
                'type': 'files',
                'media_types': ['image/png', 'image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 2',
                'type': 'file',
            }]}
        self.job_type_2 = job_test_utils.create_job_type(interface=interface_2)

        self.definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type_1.name,
                    'version': self.job_type_1.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }, {
                'name': 'Job 2',
                'job_type': {
                    'name': self.job_type_2.name,
                    'version': self.job_type_2.version,
                },
                'dependencies': [{
                    'name': 'Job 1',
                    'connections': [{
                        'output': 'Test Output 1',
                        'input': 'Test Input 2',
                    }]
                }]
            }]
        }
        self.recipe_def = RecipeDefinition(self.definition)
        self.recipe_def.validate_job_interfaces()

    def test_successful(self):
        """Tests calling RecipeTypeManager.create_recipe_type() successfully."""

        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, None)

        results_recipe_type = RecipeType.objects.get(pk=recipe_type.id)
        self.assertEqual(results_recipe_type.name, name)
        self.assertEqual(results_recipe_type.version, version)
        self.assertEqual(results_recipe_type.title, title)
        self.assertEqual(results_recipe_type.description, desc)
        self.assertDictEqual(results_recipe_type.definition, self.definition)

        results_recipe_type_rev = RecipeTypeRevision.objects.get(recipe_type_id=recipe_type.id, revision_num=1)
        self.assertDictEqual(results_recipe_type_rev.definition, self.definition)


class TestRecipeTypeManagerEditRecipeType(TransactionTestCase):

    def setUp(self):
        django.setup()

        self.workspace = storage_test_utils.create_workspace()

        interface_1 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 1',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'output_data': [{
                'name': 'Test Output 1',
                'type': 'files',
                'media_type': 'image/png',
            }]}
        self.job_type_1 = job_test_utils.create_job_type(interface=interface_1)

        interface_2 = {
            'version': '1.0',
            'command': 'my_command',
            'command_arguments': 'args',
            'input_data': [{
                'name': 'Test Input 2',
                'type': 'files',
                'media_types': ['image/png', 'image/tiff'],
            }],
            'output_data': [{
                'name': 'Test Output 2',
                'type': 'file',
            }]}
        self.job_type_2 = job_test_utils.create_job_type(interface=interface_2)

        self.definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type_1.name,
                    'version': self.job_type_1.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }, {
                'name': 'Job 2',
                'job_type': {
                    'name': self.job_type_2.name,
                    'version': self.job_type_2.version,
                },
                'dependencies': [{
                    'name': 'Job 1',
                    'connections': [{
                        'output': 'Test Output 1',
                        'input': 'Test Input 2',
                    }]
                }]
            }]
        }
        self.recipe_def = RecipeDefinition(self.definition)
        self.recipe_def.validate_job_interfaces()

        self.new_definition = {
            'version': '1.0',
            'input_data': [{
                'name': 'Recipe Input',
                'type': 'file',
                'media_types': ['text/plain'],
            }],
            'jobs': [{
                'name': 'Job 1',
                'job_type': {
                    'name': self.job_type_1.name,
                    'version': self.job_type_1.version,
                },
                'recipe_inputs': [{
                    'recipe_input': 'Recipe Input',
                    'job_input': 'Test Input 1',
                }]
            }]
        }
        self.new_recipe_def = RecipeDefinition(self.new_definition)
        self.new_recipe_def.validate_job_interfaces()

        self.configuration = {
            'version': '1.0',
            'condition': {
                'media_type': 'text/plain'
            },
            'data': {
                'input_data_name': 'Recipe Input',
                'workspace_name': self.workspace.name
            }
        }
        self.trigger_config = recipe_test_utils.MockTriggerRuleConfiguration(recipe_test_utils.MOCK_TYPE,
                                                                             self.configuration)

        self.new_configuration = {
            'version': '1.0',
            'condition': {
                'media_type': 'application/json'
            },
            'data': {
                'input_data_name': 'Recipe Input',
                'workspace_name': self.workspace.name
            }
        }
        self.new_trigger_config = recipe_test_utils.MockTriggerRuleConfiguration(recipe_test_utils.MOCK_TYPE,
                                                                                 self.new_configuration)

    def test_change_simple_no_trigger(self):
        """Tests calling RecipeTypeManager.edit_recipe_type() with only basic attributes and no previous trigger rule"""

        # Create recipe_type
        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, None)
        with transaction.atomic():
            recipe_type = RecipeType.objects.select_for_update().get(pk=recipe_type.id)
            # Edit the recipe
            new_title = 'New title'
            new_desc = 'New description'
            RecipeType.objects.edit_recipe_type(recipe_type.id, new_title, new_desc, None, None, False)
        recipe_type = RecipeType.objects.select_related('trigger_rule').get(pk=recipe_type.id)

        # Check results
        self.assertEqual(recipe_type.title, new_title)
        self.assertEqual(recipe_type.description, new_desc)
        self.assertDictEqual(recipe_type.get_recipe_definition().get_dict(), self.recipe_def.get_dict())
        self.assertEqual(recipe_type.revision_num, 1)
        self.assertIsNone(recipe_type.trigger_rule)
        num_of_revs = RecipeTypeRevision.objects.filter(recipe_type_id=recipe_type.id).count()
        self.assertEqual(num_of_revs, 1)

    def test_change_simple_with_trigger(self):
        """Tests calling RecipeTypeManager.edit_recipe_type() with only basic attributes and a previous trigger rule"""

        # Create recipe_type
        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                              configuration=self.trigger_config.get_dict())
        trigger_rule_id = trigger_rule.id
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, trigger_rule)
        with transaction.atomic():
            recipe_type = RecipeType.objects.select_for_update().get(pk=recipe_type.id)
            # Edit the recipe
            new_title = 'New title'
            new_desc = 'New description'
            RecipeType.objects.edit_recipe_type(recipe_type.id, new_title, new_desc, None, None, False)
        recipe_type = RecipeType.objects.select_related('trigger_rule').get(pk=recipe_type.id)

        # Check results
        self.assertEqual(recipe_type.title, new_title)
        self.assertEqual(recipe_type.description, new_desc)
        self.assertDictEqual(recipe_type.get_recipe_definition().get_dict(), self.recipe_def.get_dict())
        self.assertEqual(recipe_type.revision_num, 1)
        self.assertEqual(recipe_type.trigger_rule_id, trigger_rule_id)
        num_of_revs = RecipeTypeRevision.objects.filter(recipe_type_id=recipe_type.id).count()
        self.assertEqual(num_of_revs, 1)

    def test_change_to_definition(self):
        """Tests calling RecipeTypeManager.edit_recipe_type() with a change to the definition"""

        # Create recipe_type
        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                              configuration=self.trigger_config.get_dict())
        trigger_rule_id = trigger_rule.id
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, trigger_rule)
        with transaction.atomic():
            recipe_type = RecipeType.objects.select_for_update().get(pk=recipe_type.id)
            # Edit the recipe
            RecipeType.objects.edit_recipe_type(recipe_type.id, None, None, self.new_recipe_def, None, False)
        recipe_type = RecipeType.objects.select_related('trigger_rule').get(pk=recipe_type.id)

        # Check results
        self.assertEqual(recipe_type.title, title)
        self.assertEqual(recipe_type.description, desc)
        self.assertDictEqual(recipe_type.get_recipe_definition().get_dict(), self.new_recipe_def.get_dict())
        self.assertEqual(recipe_type.revision_num, 2)
        self.assertEqual(recipe_type.trigger_rule_id, trigger_rule_id)
        trigger_rule = TriggerRule.objects.get(pk=trigger_rule_id)
        self.assertTrue(trigger_rule.is_active)
        # New revision due to definition change
        num_of_revs = RecipeTypeRevision.objects.filter(recipe_type_id=recipe_type.id).count()
        self.assertEqual(num_of_revs, 2)

    def test_change_to_trigger_rule(self):
        """Tests calling RecipeTypeManager.edit_recipe_type() with a change to the trigger rule"""

        # Create recipe_type
        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                              configuration=self.trigger_config.get_dict())
        trigger_rule_id = trigger_rule.id
        new_trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                                  configuration=self.new_trigger_config.get_dict())
        new_trigger_rule_id = new_trigger_rule.id
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, trigger_rule)
        with transaction.atomic():
            recipe_type = RecipeType.objects.select_for_update().get(pk=recipe_type.id)
            # Edit the recipe
            RecipeType.objects.edit_recipe_type(recipe_type.id, None, None, None, new_trigger_rule, False)
        recipe_type = RecipeType.objects.select_related('trigger_rule').get(pk=recipe_type.id)

        # Check results
        self.assertEqual(recipe_type.title, title)
        self.assertEqual(recipe_type.description, desc)
        self.assertDictEqual(recipe_type.get_recipe_definition().get_dict(), self.recipe_def.get_dict())
        self.assertEqual(recipe_type.revision_num, 1)
        self.assertEqual(recipe_type.trigger_rule_id, new_trigger_rule_id)
        trigger_rule = TriggerRule.objects.get(pk=trigger_rule_id)
        self.assertFalse(trigger_rule.is_active)
        new_trigger_rule = TriggerRule.objects.get(pk=new_trigger_rule_id)
        self.assertTrue(new_trigger_rule.is_active)
        num_of_revs = RecipeTypeRevision.objects.filter(recipe_type_id=recipe_type.id).count()
        self.assertEqual(num_of_revs, 1)

    def test_remove_trigger_rule(self):
        """Tests calling RecipeTypeManager.edit_recipe_type() that removes the trigger rule"""

        # Create recipe_type
        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                              configuration=self.trigger_config.get_dict())
        trigger_rule_id = trigger_rule.id
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, trigger_rule)
        with transaction.atomic():
            recipe_type = RecipeType.objects.select_for_update().get(pk=recipe_type.id)
            # Edit the recipe
            RecipeType.objects.edit_recipe_type(recipe_type.id, None, None, None, None, True)
        recipe_type = RecipeType.objects.select_related('trigger_rule').get(pk=recipe_type.id)

        # Check results
        self.assertEqual(recipe_type.title, title)
        self.assertEqual(recipe_type.description, desc)
        self.assertDictEqual(recipe_type.get_recipe_definition().get_dict(), self.recipe_def.get_dict())
        self.assertEqual(recipe_type.revision_num, 1)
        self.assertIsNone(recipe_type.trigger_rule)
        trigger_rule = TriggerRule.objects.get(pk=trigger_rule_id)
        self.assertFalse(trigger_rule.is_active)
        num_of_revs = RecipeTypeRevision.objects.filter(recipe_type_id=recipe_type.id).count()
        self.assertEqual(num_of_revs, 1)

    def test_change_to_both(self):
        """Tests calling RecipeTypeManager.edit_recipe_type() with a change to both the definition and trigger rule"""

        # Create recipe_type
        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                              configuration=self.trigger_config.get_dict())
        trigger_rule_id = trigger_rule.id
        new_trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                                  configuration=self.new_trigger_config.get_dict())
        new_trigger_rule_id = new_trigger_rule.id
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, trigger_rule)
        with transaction.atomic():
            recipe_type = RecipeType.objects.select_for_update().get(pk=recipe_type.id)
            # Edit the recipe
            RecipeType.objects.edit_recipe_type(recipe_type.id, None, None, self.new_recipe_def, new_trigger_rule,
                                                False)
        recipe_type = RecipeType.objects.select_related('trigger_rule').get(pk=recipe_type.id)

        # Check results
        self.assertEqual(recipe_type.title, title)
        self.assertEqual(recipe_type.description, desc)
        self.assertDictEqual(recipe_type.get_recipe_definition().get_dict(), self.new_recipe_def.get_dict())
        self.assertEqual(recipe_type.revision_num, 2)
        self.assertEqual(recipe_type.trigger_rule_id, new_trigger_rule_id)
        trigger_rule = TriggerRule.objects.get(pk=trigger_rule_id)
        self.assertFalse(trigger_rule.is_active)
        new_trigger_rule = TriggerRule.objects.get(pk=new_trigger_rule_id)
        self.assertTrue(new_trigger_rule.is_active)
        # New revision due to definition change
        num_of_revs = RecipeTypeRevision.objects.filter(recipe_type_id=recipe_type.id).count()
        self.assertEqual(num_of_revs, 2)

    def test_invalid_trigger_rule(self):
        """Tests calling RecipeTypeManager.edit_recipe_type() with a new invalid trigger rule"""

        # Create recipe_type
        name = 'test-recipe'
        version = '1.0'
        title = 'Test Recipe'
        desc = 'Test description'
        trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_TYPE,
                                                              configuration=self.trigger_config.get_dict())
        trigger_rule_id = trigger_rule.id
        new_trigger_rule = trigger_test_utils.create_trigger_rule(trigger_type=recipe_test_utils.MOCK_ERROR_TYPE,
                                                                  configuration=self.new_trigger_config.get_dict())
        recipe_type = RecipeType.objects.create_recipe_type(name, version, title, desc, self.recipe_def, trigger_rule)
        with transaction.atomic():
            recipe_type = RecipeType.objects.select_for_update().get(pk=recipe_type.id)
            # Edit the recipe
            self.assertRaises(InvalidRecipeConnection, RecipeType.objects.edit_recipe_type, recipe_type.id, None, None,
                              self.new_recipe_def, new_trigger_rule, False)
        recipe_type = RecipeType.objects.select_related('trigger_rule').get(pk=recipe_type.id)

        # Check results
        self.assertEqual(recipe_type.title, title)
        self.assertEqual(recipe_type.description, desc)
        self.assertDictEqual(recipe_type.get_recipe_definition().get_dict(), self.recipe_def.get_dict())
        self.assertEqual(recipe_type.revision_num, 1)
        self.assertEqual(recipe_type.trigger_rule_id, trigger_rule_id)
        trigger_rule = TriggerRule.objects.get(pk=trigger_rule_id)
        self.assertTrue(trigger_rule.is_active)
        num_of_revs = RecipeTypeRevision.objects.filter(recipe_type_id=recipe_type.id).count()
        self.assertEqual(num_of_revs, 1)
