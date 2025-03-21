# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import datetime
from functools import cached_property
from typing import Any, Generic, Optional, TypeVar, Union, cast

import qai_hub as hub
from qai_hub.public_rest_api import DatasetEntries

from qai_hub_models.scorecard import (
    ScorecardCompilePath,
    ScorecardDevice,
    ScorecardProfilePath,
)

JobTypeVar = TypeVar(
    "JobTypeVar", hub.ProfileJob, hub.InferenceJob, hub.CompileJob, hub.QuantizeJob
)
ScorecardPathTypeVar = TypeVar(
    "ScorecardPathTypeVar", ScorecardCompilePath, ScorecardProfilePath
)

# Specific typevar. Autofill has trouble resolving types for nested generics without specifically listing ineritors of the generic base.
ScorecardJobTypeVar = TypeVar(
    "ScorecardJobTypeVar",
    "QuantizeScorecardJob",
    "CompileScorecardJob",
    "ProfileScorecardJob",
    "InferenceScorecardJob",
)


class ScorecardJob(Generic[JobTypeVar, ScorecardPathTypeVar]):
    job_type_class: type[JobTypeVar]

    def __init__(
        self,
        model_id: str,
        job_id: Optional[str],
        device: ScorecardDevice,
        wait_for_job: bool,  # If false, running jobs are treated like they were "skipped".
        wait_job_secs: Optional[int],  # None == any number of seconds
        path: ScorecardPathTypeVar,
    ):
        self.model_id = model_id
        self.job_id = job_id
        self._device = device
        self.wait_for_job = wait_for_job
        self.wait_job_secs = wait_job_secs
        self.path: ScorecardPathTypeVar = path
        self.__post_init__()

    def __post_init__(self):
        assert self.model_id
        # Verify Job Exists
        if self.job_id and not self.wait_for_job:
            assert self.job

        if not self.skipped and not isinstance(self.job, self.job_type_class):
            raise ValueError(
                f"Job {self.job.job_id}({self.job.name}) is {type(self.job)}. Expected {self.job_type_class.__name__}"
            )

    @cached_property
    def job(self) -> JobTypeVar:
        """
        Get the AI Hub Job.
        Waits for completion if necessary.
        """
        if not self.job_id:
            raise ValueError("No Job ID")

        job = cast(JobTypeVar, hub.get_job(self.job_id))
        if not job.get_status().finished:
            if not self.wait_for_job:
                return job
            else:
                job.wait(self.wait_job_secs)
        return job

    @cached_property
    def skipped(self) -> bool:
        #
        # Running is treated as skipped.
        #
        # Either the class would have waited for this job already,
        # or the class was told to treat running jobs like they were skipped.
        #
        return not self.job_id or self._job_status.running

    @cached_property
    def failed(self) -> bool:
        return not self.skipped and self._job_status.failure

    @cached_property
    def success(self) -> bool:
        return not self.skipped and self._job_status.success

    @cached_property
    def status_message(self) -> Optional[str]:
        return None if self.skipped else self._job_status.message

    @cached_property
    def _job_status(self) -> hub.JobStatus:
        """Get the job status of the profile job."""
        if self.job_id:
            return self.job.get_status()
        raise ValueError("Can't get status without a job ID.")

    @cached_property
    def job_status(self) -> str:
        """Get the job status of the profile job."""
        if not self.skipped:
            if self._job_status.success:
                return "Passed"
            elif self._job_status.failure:
                return "Failed"
        return "Skipped"

    @cached_property
    def device(self) -> hub.Device:
        if not self.skipped and not isinstance(self.job, hub.QuantizeJob):
            return self.job.device
        return self._device.reference_device

    @cached_property
    def chipset(self) -> str:
        """Chipset the job was run on."""
        if self.skipped:
            return self._device.chipset

        hub_device = self.device
        for attr in hub_device.attributes:
            if attr.startswith("chipset:"):
                return attr.split(":")[1]
        raise ValueError("No chipset found.")

    @cached_property
    def quantized(self) -> str:
        """Quantized models are marked so precision can be correctly recorded."""
        return (
            "Yes"
            if self.model_id.endswith("quantized")
            or self.model_id.endswith("quantizable")
            else "No"
        )

    @cached_property
    def date(self) -> Optional[datetime.datetime]:
        if self.job is None:
            return None
        return self.job.date


class QuantizeScorecardJob(ScorecardJob[hub.QuantizeJob, ScorecardCompilePath]):
    job_type_class = hub.QuantizeJob


class CompileScorecardJob(ScorecardJob[hub.CompileJob, ScorecardCompilePath]):
    job_type_class = hub.CompileJob


class ProfileScorecardJob(ScorecardJob[hub.ProfileJob, ScorecardProfilePath]):
    job_type_class = hub.ProfileJob

    def __post_init__(self):
        super().__post_init__()
        if not self.skipped and self._job_status.success:
            assert self.profile_results  # Download results immediately

    @cached_property
    def profile_results(self) -> dict[str, Any]:
        """Profile results from profile job."""
        if self.success:
            return self.job.download_profile()
        raise ValueError("Can't get profile results if job did not succeed.")

    @cached_property
    def inference_time(self) -> Union[float, str]:
        """Get the inference time from the profile job."""
        if self.success:
            return float(
                self.profile_results["execution_summary"]["estimated_inference_time"]
            )
        return "null"

    @cached_property
    def throughput(self) -> Union[float, str]:
        """Get the throughput from the profile job."""
        if not isinstance(self.inference_time, str):
            return 1000000 / float(self.inference_time)
        return "null"

    def get_layer_info(self, unit: str) -> int:
        """Count layers per compute unit."""
        if self.profile_results is not None:
            count: int = 0
            count = sum(
                1
                for detail in self.profile_results["execution_detail"]
                if detail["compute_unit"] == unit
            )
            return count
        return 0

    @cached_property
    def npu(self) -> int:
        """Get number of layers running on NPU."""
        return self.get_layer_info("NPU") if self.success else 0

    @cached_property
    def gpu(self) -> int:
        """Get number of layers running on GPU."""
        return self.get_layer_info("GPU") if self.success else 0

    @cached_property
    def cpu(self) -> int:
        """Get number of layers running on CPU."""
        return self.get_layer_info("CPU") if self.success else 0

    @cached_property
    def total(self) -> int:
        """Get the total number of layers."""
        return self.npu + self.gpu + self.cpu

    @cached_property
    def primary_compute_unit(self) -> str:
        """Get the primary compute unit."""
        layers_npu = self.npu
        layers_gpu = self.gpu
        layers_cpu = self.cpu

        if layers_npu == 0 and layers_gpu == 0 and layers_cpu == 0:
            return "null"
        compute_unit_for_most_layers = max(layers_cpu, layers_gpu, layers_npu)
        if compute_unit_for_most_layers == layers_npu:
            return "NPU"
        elif compute_unit_for_most_layers == layers_gpu:
            return "GPU"
        return "CPU"

    @cached_property
    def peak_memory_range(self) -> dict[str, int]:
        """Get the estimated peak memory range."""
        if self.success:
            low, high = self.profile_results["execution_summary"][
                "inference_memory_peak_range"
            ]
            return dict(min=low, max=high)
        return dict(min=0, max=0)

    @cached_property
    def precision(self) -> str:
        """Get the precision of the model based on the run."""
        if self.success:
            compute_unit = self.primary_compute_unit
            if compute_unit == "CPU":
                return "fp32"
            if self.quantized == "Yes":
                return "int8"
            return "fp16"
        return "null"

    @cached_property
    def performance_metrics(self) -> dict[str, Any]:
        metrics = dict(
            inference_time=self.inference_time,
            throughput=self.throughput,
            estimated_peak_memory_range=self.peak_memory_range,
            primary_compute_unit=self.primary_compute_unit,
            precision=self.precision,
            layer_info=dict(
                layers_on_npu=self.npu,
                layers_on_gpu=self.gpu,
                layers_on_cpu=self.cpu,
                total_layers=self.total,
            ),
            job_id=self.job_id,
            job_status=self.job_status,
        )
        return metrics


class InferenceScorecardJob(ScorecardJob[hub.InferenceJob, ScorecardProfilePath]):
    job_type_class = hub.InferenceJob

    @property
    def input_dataset(self) -> DatasetEntries:
        """Input dataset."""
        return cast(DatasetEntries, self.job.inputs.download())

    @property
    def output_dataset(self) -> DatasetEntries:
        """Output dataset."""
        if not self.success:
            raise ValueError("Can't get output dataset if job did not succeed.")
        return cast(DatasetEntries, self.job.download_output_data())
