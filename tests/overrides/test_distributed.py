# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from collections.abc import Iterable

import pytest
from torch.utils.data import BatchSampler, SequentialSampler
from torch.utils.data.sampler import RandomSampler

from pytorch_lightning import seed_everything
from pytorch_lightning.overrides.distributed import (
    FastForwardSampler,
    IndexBatchSamplerWrapper,
    UnrepeatedDistributedSampler,
)
from pytorch_lightning.utilities.data import has_len


@pytest.mark.parametrize("shuffle", [False, True])
def test_unrepeated_distributed_sampler(shuffle, tmpdir):
    """Test each rank will receive a different number of elements."""

    seed_everything(42)
    world_size = 4
    samplers = []
    dataset = range(103)
    for rank in range(world_size):
        samplers.append(UnrepeatedDistributedSampler(dataset, rank=rank, num_replicas=world_size, shuffle=shuffle))

    indices = [list(s) for s in samplers]
    assert len(indices[0]) == 26
    assert len(indices[1]) == 26
    assert len(indices[2]) == 26
    assert len(indices[3]) == 25

    assert indices[0][-1] == 18 if shuffle else 100
    assert indices[1][-1] == 30 if shuffle else 101
    assert indices[2][-1] == 29 if shuffle else 102
    assert indices[3][-1] == 35 if shuffle else 99


def test_index_batch_sampler(tmpdir):
    """Test `IndexBatchSampler` properly extracts indices."""
    dataset = range(15)
    sampler = SequentialSampler(dataset)
    batch_sampler = BatchSampler(sampler, 3, False)
    index_batch_sampler = IndexBatchSamplerWrapper(batch_sampler)

    assert batch_sampler.batch_size == index_batch_sampler.batch_size
    assert batch_sampler.drop_last == index_batch_sampler.drop_last
    assert batch_sampler.sampler is sampler

    for batch in index_batch_sampler:
        assert index_batch_sampler.batch_indices == batch


def test_index_batch_sampler_methods():
    dataset = range(15)
    sampler = SequentialSampler(dataset)
    batch_sampler = BatchSampler(sampler, 3, False)
    index_batch_sampler = IndexBatchSamplerWrapper(batch_sampler)

    assert isinstance(index_batch_sampler, Iterable)
    assert has_len(index_batch_sampler)


def test_fast_forward_on_batch_sampler():
    dataset = range(15)
    sampler = SequentialSampler(dataset)
    batch_sampler = BatchSampler(sampler, 3, False)
    index_batch_sampler = FastForwardSampler(batch_sampler)

    assert isinstance(index_batch_sampler, Iterable)
    assert has_len(index_batch_sampler)

    index_batch_sampler_iter = iter(index_batch_sampler)

    assert next(index_batch_sampler_iter) == [0, 1, 2]
    assert next(index_batch_sampler_iter) == [3, 4, 5]

    state_dict = index_batch_sampler.state_dict()
    assert state_dict["current_iteration"] == 2

    dataset = range(15)
    sampler = SequentialSampler(dataset)
    batch_sampler = BatchSampler(sampler, 3, False)
    index_batch_sampler = FastForwardSampler(batch_sampler)
    index_batch_sampler.load_state_dict(state_dict)

    index_batch_sampler_iter = iter(index_batch_sampler)
    assert next(index_batch_sampler_iter) == [6, 7, 8]


def test_fast_forward_on_sequential_sampler():
    dataset = range(15)
    sampler = FastForwardSampler(SequentialSampler(dataset))
    batch_sampler = BatchSampler(sampler, 3, False)

    batch_sampler_iter = iter(batch_sampler)

    assert next(batch_sampler_iter) == [0, 1, 2]
    assert next(batch_sampler_iter) == [3, 4, 5]

    state_dict = sampler.state_dict()
    assert state_dict["current_iteration"] == 6

    dataset = range(15)
    sampler = FastForwardSampler(SequentialSampler(dataset))
    batch_sampler = BatchSampler(sampler, 3, False)
    sampler.load_state_dict(state_dict)

    batch_sampler_iter = iter(batch_sampler)
    assert next(batch_sampler_iter) == [6, 7, 8]


def test_fast_forward_on_random_sampler():
    seed_everything(42)

    dataset = range(15)
    sampler = FastForwardSampler(RandomSampler(dataset))
    batch_sampler = BatchSampler(sampler, 3, False)

    batch_sampler_iter = iter(batch_sampler)

    assert next(batch_sampler_iter) == [14, 9, 1]
    assert next(batch_sampler_iter) == [7, 11, 3]
    assert next(batch_sampler_iter) == [12, 8, 2]

    state_dict = sampler.state_dict()
    assert state_dict["current_iteration"] == 9
    state_dict["current_iteration"] = 6

    dataset = range(15)
    sampler = FastForwardSampler(RandomSampler(dataset))
    batch_sampler = BatchSampler(sampler, 3, False)
    sampler.load_state_dict(state_dict)

    batch_sampler_iter = iter(batch_sampler)
    assert next(batch_sampler_iter) == [12, 8, 2]
    has_raised = False
    try:
        for _ in range(5):
            next(batch_sampler_iter)
    except StopIteration:
        has_raised = True
        assert sampler.rng_state is None
        assert sampler.current_iteration == 0
        sampler.load_state_dict(sampler.state_dict())
    assert has_raised
