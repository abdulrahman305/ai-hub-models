# ---------------------------------------------------------------------
# Copyright (c) 2024 Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
# THIS FILE WAS AUTO-GENERATED. DO NOT EDIT MANUALLY.


from __future__ import annotations

import warnings

import qai_hub as hub

from qai_hub_models.models.sesr_m5_quantized import MODEL_ID, Model
from qai_hub_models.utils.args import evaluate_parser, get_hub_device, get_model_kwargs
from qai_hub_models.utils.evaluate import evaluate_on_dataset
from qai_hub_models.utils.inference import compile_model_from_args

SUPPORTED_DATASETS = ["bsd300"]


def main():
    warnings.filterwarnings("ignore")
    parser = evaluate_parser(
        model_cls=Model,
        default_split_size=100,
        default_num_samples=100,
        supported_datasets=SUPPORTED_DATASETS,
        is_hub_quantized=True,
    )
    args = parser.parse_args()
    args.device = None

    if args.hub_model_id is not None:
        hub_model = hub.get_model(args.hub_model_id)
    else:
        hub_model = compile_model_from_args(
            MODEL_ID, args, get_model_kwargs(Model, vars(args))
        )
    hub_device = get_hub_device(None, args.chipset)
    torch_model = Model.from_pretrained(**get_model_kwargs(Model, vars(args)))
    evaluate_on_dataset(
        hub_model,
        torch_model,
        hub_device,
        args.dataset_name,
        args.split_size,
        args.num_samples,
        args.seed,
        args.profile_options,
        args.use_dataset_cache,
        args.compute_quant_cpu_accuracy,
    )


if __name__ == "__main__":
    main()
