"""Defines the QueueEventProcessor for generating file ancestry links as job executions change status."""
from product.models import FileAncestryLink, ProductFile
from queue.models import QueueEventProcessor


class ProductProcessor(QueueEventProcessor):
    """This class creates file ancestry links when a job execution is queued or completed."""

    def process_queued(self, job_exe, is_initial):
        """See :meth:`queue.models.QueueEventProcessor.process_queued`.

        Creates file ancestry links for all source files and their ancestry needed to run the job execution.
        """
        # Build file ancestry links for all job input files the first time the job is queued
        # This provides linkage of source files to jobs and recipes even when no products are ultimately created
        if is_initial:
            input_file_ids = job_exe.job.get_job_data().get_input_file_ids()
            FileAncestryLink.objects.create_file_ancestry_links(input_file_ids, None, job_exe)

    def process_completed(self, job_exe):
        """See :meth:`queue.models.QueueEventProcessor.process_completed`.

        Creates file ancestry links for all products generated by a job execution, including the source file ancestry.
        """
        ProductFile.objects.publish_products(job_exe, job_exe.ended)

    def process_failed(self, job_exe):
        """See :meth:`queue.models.QueueEventProcessor.process_failed`.

        Not used by this class.
        """
        pass
