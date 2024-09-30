from dataclasses import dataclass
from reason.inference.lm_call import LMCallingConfig, VLLMRemoteCaller
from reason.inference.rm_call import RMRemoteCaller
from reason.evaluation.evaluator import SolutionOutput, Task
from reason.mcts.tree import SearchTree


@dataclass
class BasicConfig:
    task_name: str


@dataclass
class CoTConfig(BasicConfig):
    pass


def cot(
    config: CoTConfig,
    gen_config: LMCallingConfig,
    problem_inst,
    llm_call: VLLMRemoteCaller,
    rm_call: RMRemoteCaller,
) -> SolutionOutput:
    gen_config = LMCallingConfig(
        n=1,
        temperature=0,
        top_k=1,
        top_p=1.0,
        max_new_tokens=gen_config.max_new_tokens,
    )
    config.num_sequence = 1
    return best_of_n(config, gen_config, problem_inst, llm_call, rm_call)


@dataclass
class BestOfNConfig(BasicConfig):
    num_sequence: int = 32


def best_of_n(
    config: BestOfNConfig,
    gen_config: LMCallingConfig,
    problem_inst,
    lm_call: VLLMRemoteCaller,
    rm_call: RMRemoteCaller,
) -> SolutionOutput:
    if gen_config.max_new_tokens < 256:
        print("Warning: max_new_tokens is less than 256")

    gen_config.n = config.num_sequence
    task = Task(task_name=config.task_name)
    prompt = task.prompt_fn(problem_inst["question"])
    output = lm_call(prompt, gen_config)
    completion_tokens = [0] * len(output.text)
    completion_tokens[-1] = output.completion_tokens
    return SolutionOutput(
        solutions=output.text,
        completion_tokens=completion_tokens,
    )


@dataclass
class TreeSearchConfig(BasicConfig):
    tree_max_width: int = 10
    tree_max_length: int = 10


@dataclass
class BeamSearchConfig(TreeSearchConfig):
    beam_size: int = 1


def beam_search(
    config: BeamSearchConfig,
    gen_config: LMCallingConfig,
    problem_inst,
    lm_call: VLLMRemoteCaller,
    rm_call: RMRemoteCaller,
) -> SolutionOutput:
    task = Task(task_name=config.task_name)
    # Hack here
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        "/hpc2ssd/JH_DATA/spooler/qxiao183/workspace/hf_models/peiyi9979/mistral-7b-sft"
    )
    env = task.env_fn(
        config={
            "max_actions": config.tree_max_width,
            "max_length": config.tree_max_length,
            "stop_str": "The answer is ",
            "generation_config": {
                "max_new_tokens": gen_config.max_new_tokens,
                "temperature": gen_config.temperature,
                "top_p": gen_config.top_p,
                "top_k": gen_config.top_k,
            },
        },
        math_problems=[
            {
                "question": problem_inst["question"],
                "answer": task.extract_groundtruth(problem_inst["answer"]),
            }
        ],
        llm_gen_fn=lm_call,
        tokenizer=tokenizer,
    )

    search_tree = SearchTree(cfg={})
    traj_list = search_tree.beam_search(env, config.beam_size, config.tree_max_length, rm_call)
    return SolutionOutput(
        solutions=[t['text'] for t in traj_list],
        completion_tokens=[t['num_generated_token'] for t in traj_list]
    )