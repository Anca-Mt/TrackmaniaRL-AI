"""
==============================================================================
COMPETITION TUTORIAL #1: Custom model and RL algorithm
==============================================================================

In this tutorial, we will customize the TrackMania training pipeline.

The tutorial works with the TrackMania FULL Gymnasium environment.
Please refer to the README on GitHub to set up this environment in config.json:
https://github.com/trackmania-rl/tmrl#full-environment

Note: This tutorial describes implementing and running a TrainingAgent along with an ActorModule.
It is relevant if you want to implement your own RL approaches in TrackMania.
If you plan to try non-RL approaches instead, this is also accepted in the competition:
just use the Gymnasium Full environment and do whatever you need,
then, wrap your trained policy in an ActorModule, and submit your entry :)

Copy and adapt this script to implement your own algorithm/model in TrackMania.
Then, use the script as follows:

To launch the Server, provided the script is named custom_actor_module.py, execute:
python custom_actor_module.py --server

In another terminal, launch the Trainer:
python custom_actor_module.py --trainer

And in yet another terminal, launch a RolloutWorker:
python custom_actor_module.py --worker

You can launch these in any order, but we recommend server, then trainer, then worker.
If you are running everything on the same machine, your trainer may consume all your resource,
resulting in your worker struggling to collect samples in a timely fashion.
If your worker crazily warns you about time-steps timing out, this is probably the issue.
The best way of using TMRL with TrackMania is to have your worker(s) and trainer on separate machines.
The server can run on either of these machines, or yet another machine that both can reach via network.
Achieving this is easy (and is also kind of the whole point of the TMRL framework).
Just adapt config.json (or this script) to your network configuration.
In particular, you will want to set the following in the TMRL config.json file of all your machines:

"LOCALHOST_WORKER": false,
"LOCALHOST_TRAINER": false,
"PUBLIC_IP_SERVER": "<ip.of.the.server>",
"PORT": <port of the server (usually requires port forwarding if accessed via the Internet)>,

If you are training over the Internet, please read the security instructions on the TMRL GitHub page.

IMPORTANT: Set a custom 'RUN_NAME' in config.json, otherwise this script will not work.
"""

# Let us start our tutorial by importing some useful stuff.

# The constants that are defined in config.json:
import tmrl.config.config_constants as cfg
# Useful classes:
import tmrl.config.config_objects as cfg_obj
# The utility that TMRL uses to partially instantiate classes:
from tmrl.util import partial
# The TMRL three main entities (i.e., the Trainer, the RolloutWorker and the central Server):
from tmrl.networking import Trainer, RolloutWorker, Server

# The training class that we will customize with our own training algorithm in this tutorial:
from tmrl.training_offline import TrainingOffline

# And a couple external libraries:
import numpy as np
import os


# Now, let us look into the content of config.json:

# =====================================================================
# USEFUL PARAMETERS
# =====================================================================
# You can change these parameters here directly (not recommended),
# or you can change them in the TMRL config.json file (recommended).

# Maximum number of training 'epochs':
# (training is checkpointed at the end of each 'epoch', this is also when training metrics can be logged to wandb)
epochs = cfg.TMRL_CONFIG["MAX_EPOCHS"]

# Number of rounds per 'epoch':
# (training metrics are displayed in the terminal at the end of each round)
rounds = cfg.TMRL_CONFIG["ROUNDS_PER_EPOCH"]

# Number of training steps per round:
# (a training step is a call to the train() function that we will define later in this tutorial)
steps = cfg.TMRL_CONFIG["TRAINING_STEPS_PER_ROUND"]

# Minimum number of environment steps collected before training starts:
# (this is useful when you want to fill your replay buffer with samples from a baseline policy)
start_training = cfg.TMRL_CONFIG["ENVIRONMENT_STEPS_BEFORE_TRAINING"]

# Maximum training steps / environment steps ratio:
# (if training becomes faster than this ratio, it will be paused, waiting for new samples from the environment)
max_training_steps_per_env_step = cfg.TMRL_CONFIG["MAX_TRAINING_STEPS_PER_ENVIRONMENT_STEP"]

# Number of training steps performed between broadcasts of policy updates:
update_model_interval = cfg.TMRL_CONFIG["UPDATE_MODEL_INTERVAL"]

# Number of training steps performed between retrievals of received samples to put them in the replay buffer:
update_buffer_interval = cfg.TMRL_CONFIG["UPDATE_BUFFER_INTERVAL"]

# Training device (e.g., "cuda:0"):
device_trainer = 'cuda' if cfg.CUDA_TRAINING else 'cpu'

# Maximum size of the replay buffer:
memory_size = cfg.TMRL_CONFIG["MEMORY_SIZE"]

# Batch size for training:
batch_size = cfg.TMRL_CONFIG["BATCH_SIZE"]

# Wandb credentials:
# (Change this with your own if you want to keep your training curves private)
# (Also, please use your own wandb account if you are going to log huge stuff :) )

wandb_run_id = cfg.WANDB_RUN_ID  # change this by a name of your choice for your run
wandb_project = cfg.TMRL_CONFIG["WANDB_PROJECT"]  # name of the wandb project in which your run will appear
wandb_entity = cfg.TMRL_CONFIG["WANDB_ENTITY"]  # wandb account
wandb_key = cfg.TMRL_CONFIG["WANDB_KEY"]  # wandb API key

os.environ['WANDB_API_KEY'] = wandb_key  # this line sets your wandb API key as the active key

# Number of time-steps after which episodes collected by the worker are truncated:
max_samples_per_episode = cfg.TMRL_CONFIG["RW_MAX_SAMPLES_PER_EPISODE"]

# Networking parameters:
# (In TMRL, networking is managed by tlspyo. The following are tlspyo parameters.)
server_ip_for_trainer = cfg.SERVER_IP_FOR_TRAINER  # IP of the machine running the Server (trainer point of view)
server_ip_for_worker = cfg.SERVER_IP_FOR_WORKER  # IP of the machine running the Server (worker point of view)
server_port = cfg.PORT  # port used to communicate with this machine
password = cfg.PASSWORD  # password that secures your communication
security = cfg.SECURITY  # when training over the Internet, it is safer to change this to "TLS"
# (please read the security instructions on GitHub)


# =====================================================================
# ADVANCED PARAMETERS
# =====================================================================
# You may want to change the following in advanced applications;
# however, most competitors will not need to change this.
# If interested, read the full TMRL tutorial on GitHub.
# These parameters are to change here directly (if you want).
# (Note: The tutorial may stop working if you change these)

# Base class of the replay memory used by the trainer:
memory_base_cls = cfg_obj.MEM

# Sample compression scheme applied by the worker for this replay memory:
sample_compressor = cfg_obj.SAMPLE_COMPRESSOR

# Sample preprocessor for data augmentation:
sample_preprocessor = None

# Path from where an offline dataset can be loaded to initialize the replay memory:
dataset_path = cfg.DATASET_PATH

# Preprocessor applied by the worker to the observations it collects:
# (Note: if your script defines the name "obs_preprocessor", we will use your preprocessor instead of the default)
obs_preprocessor = cfg_obj.OBS_PREPROCESSOR


# =====================================================================
# COMPETITION FIXED PARAMETERS
# =====================================================================
# Competitors CANNOT change the following parameters.

# rtgym environment class (full TrackMania Gymnasium environment):
env_cls = cfg_obj.ENV_CLS

# Device used for inference on workers (change if you like but keep in mind that the competition evaluation is on CPU)
device_worker = 'cpu'


# =====================================================================
# ENVIRONMENT PARAMETERS
# =====================================================================
# You are allowed to customize these environment parameters.
# Do not change these here though, customize them in config.json.
# Your environment configuration must be part of your submission,
# e.g., the "ENV" entry of your config.json file.

# Dimensions of the TrackMania window:
window_width = cfg.WINDOW_WIDTH  # must be between 256 and 958
window_height = cfg.WINDOW_HEIGHT  # must be between 128 and 488

# Dimensions of the actual images in observations:
img_width = cfg.IMG_WIDTH
img_height = cfg.IMG_HEIGHT

# Whether you are using grayscale (default) or color images:
# (Note: The tutorial will stop working if you use colors)
img_grayscale = cfg.GRAYSCALE

# Number of consecutive screenshots in each observation:
imgs_buf_len = cfg.IMG_HIST_LEN

# Number of actions in the action buffer (this is part of observations):
# (Note: The tutorial will stop working if you change this)
act_buf_len = cfg.ACT_BUF_LEN


# =====================================================================
# MEMORY CLASS
# =====================================================================
# Nothing to do here.
# This is the memory class passed to the Trainer.
# If you need a custom memory, change the relevant advanced parameters.
# Custom memories are described in the full TMRL tutorial.

memory_cls = partial(memory_base_cls,
                     memory_size=memory_size,
                     batch_size=batch_size,
                     sample_preprocessor=sample_preprocessor,
                     dataset_path=cfg.DATASET_PATH,
                     imgs_obs=imgs_buf_len,
                     act_buf_len=act_buf_len,
                     crc_debug=False)


# =====================================================================
# CUSTOM MODEL
# =====================================================================
# Alright, now for the fun part.
# Our goal in this competition is to come up with the best trained
# ActorModule for TrackMania 2020, where an 'ActorModule' is a policy.
# In this tutorial, we present a deep RL way of tackling this problem:
# we implement our own deep neural network architecture (ActorModule),
# and then we implement our own RL algorithm to train this module.

# We will implement SAC and a hybrid CNN/MLP model.

# The following constants are from the Spinup implementation of SAC
# that we simply copy/paste and adapt in this tutorial.
LOG_STD_MAX = 2
LOG_STD_MIN = -20


# Let us import the ActorModule that we are supposed to implement.
# We will use PyTorch in this tutorial.
# TMRL readily provides a PyTorch-specific subclass of ActorModule:
from tmrl.actor import TorchActorModule

# Plus a couple useful imports:
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions.normal import Normal
from math import floor


# In the full version of the TrackMania 2020 environment, the
# observation-space comprises a history of screenshots. Thus, we need
# Computer Vision layers such as a CNN in our model to process these.
# The observation space also comprises single floats representing speed,
# rpm and gear. We will merge these with the information contained in
# screenshots thanks to an MLP following our CNN layers.


# Here is the MLP:
def mlp(sizes, activation, output_activation=nn.Identity):
    """
    A simple MLP (MultiLayer Perceptron).

    Args:
        sizes: list of integers representing the hidden size of each layer
        activation: activation function of hidden layers
        output_activation: activation function of the last layer

    Returns:
        Our MLP in the form of a Pytorch Sequential module
    """
    layers = []
    for j in range(len(sizes) - 1):
        act = activation if j < len(sizes) - 2 else output_activation
        layers += [nn.Linear(sizes[j], sizes[j + 1]), act()]
    return nn.Sequential(*layers)


# The next utility computes the dimensionality of CNN feature maps when flattened together:
def num_flat_features(x):
    size = x.size()[1:]  # dimension 0 is the batch dimension, so it is ignored
    num_features = 1
    for s in size:
        num_features *= s
    return num_features


# The next utility computes the dimensionality of the output in a 2D CNN layer:
def conv2d_out_dims(conv_layer, h_in, w_in):
    h_out = floor((h_in + 2 * conv_layer.padding[0] - conv_layer.dilation[0] * (conv_layer.kernel_size[0] - 1) - 1) / conv_layer.stride[0] + 1)
    w_out = floor((w_in + 2 * conv_layer.padding[1] - conv_layer.dilation[1] * (conv_layer.kernel_size[1] - 1) - 1) / conv_layer.stride[1] + 1)
    return h_out, w_out


# Let us now define a module that will be the main building block of both our actor and critic:
class VanillaCNN(nn.Module):
    def __init__(self, q_net):
        """
        Simple CNN (Convolutional Neural Network) model for SAC (Soft Actor-Critic).

        Args:
            q_net (bool): indicates whether this neural net is a critic network
        """
        super(VanillaCNN, self).__init__()

        self.q_net = q_net

        # Convolutional layers processing screenshots:
        # The default config.json gives 4 grayscale images of 64 x 64 pixels
        self.h_out, self.w_out = img_height, img_width
        self.conv1 = nn.Conv2d(imgs_buf_len, 64, 8, stride=2)
        self.h_out, self.w_out = conv2d_out_dims(self.conv1, self.h_out, self.w_out)
        self.conv2 = nn.Conv2d(64, 64, 4, stride=2)
        self.h_out, self.w_out = conv2d_out_dims(self.conv2, self.h_out, self.w_out)
        self.conv3 = nn.Conv2d(64, 128, 4, stride=2)
        self.h_out, self.w_out = conv2d_out_dims(self.conv3, self.h_out, self.w_out)
        self.conv4 = nn.Conv2d(128, 128, 4, stride=2)
        self.h_out, self.w_out = conv2d_out_dims(self.conv4, self.h_out, self.w_out)
        self.out_channels = self.conv4.out_channels

        # Dimensionality of the CNN output:
        self.flat_features = self.out_channels * self.h_out * self.w_out

        # Dimensionality of the MLP input:
        # The MLP input will be formed of:
        # - the flattened CNN output
        # - the current speed, gear and RPM measurements (3 floats)
        # - the 2 previous actions (2 x 3 floats), important because of the real-time nature of our controller
        # - when the module is the critic, the selected action (3 floats)
        float_features = 12 if self.q_net else 9
        self.mlp_input_features = self.flat_features + float_features

        # MLP layers:
        # (when using the model as a policy, we will sample from a multivariate gaussian defined later in the tutorial;
        # thus, the output dimensionality is  1 for the critic, and we will define the output layer of policies later)
        self.mlp_layers = [256, 256, 1] if self.q_net else [256, 256]
        self.mlp = mlp([self.mlp_input_features] + self.mlp_layers, nn.ReLU)

    def forward(self, x):
        """
        In Pytorch, the forward function is where our neural network computes its output from its input.

        Args:
            x (torch.Tensor): input tensor (i.e., the observation fed to our deep neural network)

        Returns:
            the output of our neural network in the form of a torch.Tensor
        """
        if self.q_net:
            # The critic takes the next action (act) as additional input
            # act1 and act2 are the actions in the action buffer (real-time RL):
            speed, gear, rpm, images, act1, act2, act = x
        else:
            # For the policy, the next action (act) is what we are computing, so we don't have it:
            speed, gear, rpm, images, act1, act2 = x

        # Forward pass of our images in the CNN:
        # (note that the competition environment outputs histories of 4 images
        # and the default config outputs these as 64 x 64 greyscale,
        # we will stack these greyscale images along the channel dimension of our input tensor)
        x = F.relu(self.conv1(images))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = F.relu(self.conv4(x))

        # Now we will flatten our output feature map.
        # Let us double-check that our dimensions are what we expect them to be:
        flat_features = num_flat_features(x)
        assert flat_features == self.flat_features, f"x.shape:{x.shape},\
                                                    flat_features:{flat_features},\
                                                    self.out_channels:{self.out_channels},\
                                                    self.h_out:{self.h_out},\
                                                    self.w_out:{self.w_out}"
        # All good, let us flatten our output feature map:
        x = x.view(-1, flat_features)

        # Finally, we can feed the result along our float values to the MLP:
        if self.q_net:
            x = torch.cat((speed, gear, rpm, x, act1, act2, act), -1)
        else:
            x = torch.cat((speed, gear, rpm, x, act1, act2), -1)
        x = self.mlp(x)

        # And this gives us the output of our deep neural network :)
        return x


# We can now implement the TMRL ActorModule interface that we are supposed to submit for this competition.

# During training, TMRL will regularly save our trained ActorModule in the TmrlData/weights folder.
# By default, this would be done using the torch (i.e., pickle) serializer.
# However, while saving and loading your own pickle files is fine,
# it is highly dangerous to load other people's pickle files.
# Therefore, the competition submission does not accept pickle files.
# Instead, we can submit our trained weights in the form of a human-readable JSON file.
# The ActorModule interface defines save() and load() methods that we will override with our own JSON serializer.

import json


class TorchJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for torch tensors, used in the custom save() method of our ActorModule.
    """
    def default(self, obj):
        if isinstance(obj, torch.Tensor):
            return obj.cpu().detach().numpy().tolist()
        return json.JSONEncoder.default(self, obj)


class TorchJSONDecoder(json.JSONDecoder):
    """
    Custom JSON decoder for torch tensors, used in the custom load() method of our ActorModule.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, dct):
        for key in dct.keys():
            if isinstance(dct[key], list):
                dct[key] = torch.Tensor(dct[key])
        return dct


class MyActorModule(TorchActorModule):
    """
    Our policy wrapped in the TMRL ActorModule class.

    The only required method is ActorModule.act().
    We also implement a forward() method for our training algorithm.

    (Note: TorchActorModule is a subclass of ActorModule and torch.nn.Module)
    """
    def __init__(self, observation_space, action_space):
        """
        When implementing __init__, we need to take the observation_space and action_space arguments.

        Args:
            observation_space: observation space of the Gymnasium environment
            action_space: action space of the Gymnasium environment
        """
        # We must call the superclass __init__:
        super().__init__(observation_space, action_space)

        # And initialize our attributes:
        dim_act = action_space.shape[0]  # dimensionality of actions
        act_limit = action_space.high[0]  # maximum amplitude of actions
        # Our hybrid CNN+MLP policy:
        self.net = VanillaCNN(q_net=False)
        # The policy output layer, which samples actions stochastically in a gaussian, with means...:
        self.mu_layer = nn.Linear(256, dim_act)
        # ... and log standard deviations:
        self.log_std_layer = nn.Linear(256, dim_act)
        # We will squash this within the action space thanks to a tanh final activation:
        self.act_limit = act_limit

    def save(self, path):
        """
        JSON-serialize a detached copy of the ActorModule and save it in path.

        IMPORTANT: FOR THE COMPETITION, WE ONLY ACCEPT JSON AND PYTHON FILES.
        IN PARTICULAR, WE *DO NOT* ACCEPT PICKLE FILES (such as output by torch.save()...).

        All your submitted files must be human-readable, for everyone's safety.
        Indeed, untrusted pickle files are an open door for hackers.

        Args:
            path: pathlib.Path: path to where the object will be stored.
        """
        with open(path, 'w') as json_file:
            json.dump(self.state_dict(), json_file, cls=TorchJSONEncoder)
        # torch.save(self.state_dict(), path)

    def load(self, path, device):
        """
        Load the parameters of your trained ActorModule from a JSON file.

        Adapt this method to your submission so that we can load your trained ActorModule.

        Args:
            path: pathlib.Path: full path of the JSON file
            device: str: device on which the ActorModule should live (e.g., "cpu")

        Returns:
            The loaded ActorModule instance
        """
        self.device = device
        with open(path, 'r') as json_file:
            state_dict = json.load(json_file, cls=TorchJSONDecoder)
        self.load_state_dict(state_dict)
        self.to_device(device)
        # self.load_state_dict(torch.load(path, map_location=self.device))
        return self

    def forward(self, obs, test=False, compute_logprob=True):
        """
        Computes the output action of our policy from the input observation.

        The whole point of deep RL is to train our policy network (actor) such that it outputs relevant actions.
        Training per-se will also rely on a critic network, but this is not part of the trained policy.
        Thus, our ActorModule will only implement the actor.

        Args:
            obs: the observation from the Gymnasium environment (when using TorchActorModule this is a torch.Tensor)
            test (bool): this is True for test episodes (deployment) and False for training episodes;
                in SAC, this enables us to sample randomly during training and deterministically at test-time.
            compute_logprob (bool): SAC will set this to True to retrieve log probabilities.

        Returns:
            the action sampled from our policy from observation obs
            the log probability of this action (this will be used for SAC)
        """
        # obs is our input observation.
        # We feed it to our actor neural network, which will output an action.

        # Let us feed it to our MLP:
        net_out = self.net(obs)
        # Now, the means of our multivariate gaussian (i.e., Normal law) are:
        mu = self.mu_layer(net_out)
        # And the corresponding standard deviations are:
        log_std = self.log_std_layer(net_out)
        log_std = torch.clamp(log_std, LOG_STD_MIN, LOG_STD_MAX)
        std = torch.exp(log_std)
        # We can now sample our action in the resulting multivariate gaussian (Normal) distribution:
        pi_distribution = Normal(mu, std)
        if test:
            pi_action = mu  # at test time, our action is deterministic (it is just the means)
        else:
            pi_action = pi_distribution.rsample()  # during training, it is sampled in the multivariate gaussian
        # We retrieve the log probabilities of our multivariate gaussian as they will be useful for SAC:
        if compute_logprob:
            logp_pi = pi_distribution.log_prob(pi_action).sum(axis=-1)
            # (the next line is a correction formula for TanH squashing, present in the Spinup implementation of SAC)
            logp_pi -= (2 * (np.log(2) - pi_action - F.softplus(-2 * pi_action))).sum(axis=1)
        else:
            logp_pi = None
        # And we squash our action within the action space:
        pi_action = torch.tanh(pi_action)
        pi_action = self.act_limit * pi_action
        # Finally, we remove the batch dimension:
        pi_action = pi_action.squeeze()
        return pi_action, logp_pi

    # Now, the only method that all participants are required to implement is act()
    # act() is the interface for TMRL to use your ActorModule as the policy it tests in TrackMania.
    # For the evaluation, the "test" argument will be set to True.
    def act(self, obs, test=False):
        """
        Computes an action from an observation.

        This method is the one all participants must implement.
        It is the policy that TMRL will use in TrackMania to evaluate your submission.

        Args:
            obs (object): the input observation (when using TorchActorModule, this is a torch.Tensor)
            test (bool): True at test-time (e.g., during evaluation...), False otherwise

        Returns:
            act (numpy.array): the computed action, in the form of a numpy array of 3 values between -1.0 and 1.0
        """
        # Since we have already implemented our policy in the form of a neural network,
        # act() is now pretty straightforward.
        # We don't need to compute the log probabilities here (they will be for our SAC training algorithm).
        # Also note that, when using TorchActorModule, TMRL calls act() in a torch.no_grad() context.
        # Thus, you don't need to use "with torch.no_grad()" here.
        # But let us do it anyway to be extra sure, for the people using ActorModule instead of TorchActorModule.
        with torch.no_grad():
            a, _ = self.forward(obs=obs, test=test, compute_logprob=False)
            return a.cpu().numpy()


# The critic module for SAC is now super straightforward:
class VanillaCNNQFunction(nn.Module):
    """
    Critic module for SAC.
    """
    def __init__(self, observation_space, action_space):
        super().__init__()
        self.net = VanillaCNN(q_net=True)  # q_net is True for a critic module

    def forward(self, obs, act):
        """
        Estimates the action-value of the (obs, act) state-action pair.

        In RL theory, the action-value is the expected sum of (gamma-discounted) future rewards
        when observing obs, taking action act, and following the current policy ever after.

        Args:
            obs: current observation
            act: tried next action

        Returns:
            The action-value of act in situation obs, as estimated by our critic network
        """
        # Since q_net is True, we append our action act to our observation obs.
        # Note that obs is a tuple of batched tensors: respectively the history of 4 images, speed, etc.
        x = (*obs, act)
        q = self.net(x)
        return torch.squeeze(q, -1)


# Finally, let us merge this together into an actor-critic torch.nn.module for training.
# Classically, we use one actor and two parallel critics to alleviate the overestimation bias.
class VanillaCNNActorCritic(nn.Module):
    """
    Actor-critic module for the SAC algorithm.
    """
    def __init__(self, observation_space, action_space):
        super().__init__()

        # Policy network (actor):
        self.actor = MyActorModule(observation_space, action_space)
        # Value networks (critics):
        self.q1 = VanillaCNNQFunction(observation_space, action_space)
        self.q2 = VanillaCNNQFunction(observation_space, action_space)


# =====================================================================
# CUSTOM TRAINING ALGORITHM
# =====================================================================
# So far, we have implemented our custom model.
# We have also wrapped it in an ActorModule, which we will train and
# submit as an entry to the TMRL competition.
# Our ActorModule will be used in Workers to collect training data.
# Our VanillaCNNActorCritic will be used in the Trainer for training
# this ActorModule. Let us now tackle the training algorithm per-se.
# In TMRL, this is done by implementing a custom TrainingAgent.

from tmrl.training import TrainingAgent

# We will also use a couple utilities, and the Adam optimizer:

from tmrl.custom.utils.nn import copy_shared, no_grad
from tmrl.util import cached_property
from copy import deepcopy
import itertools
from torch.optim import Adam


# A TrainingAgent must implement two methods:
# -> train(batch): optimizes the model from a batch of RL samples
# -> get_actor(): outputs a copy of the current ActorModule
# In this tutorial, we implement the Soft Actor-Critic algorithm
# by adapting the OpenAI Spinup implementation.

class PPOTrainingAgent(TrainingAgent):
    model_nograd = cached_property(lambda self: no_grad(copy_shared(self.model)))

    def __init__(self,
                 observation_space=None,
                 action_space=None,
                 device=None,
                 model_cls=VanillaCNNActorCritic,
                 gamma=0.99,
                 lam=0.95,
                 clip_ratio=0.2,
                 pi_lr=3e-4,
                 vf_lr=1e-3,
                 train_pi_iters=80,
                 train_v_iters=80,
                 target_kl=0.01):
        super().__init__(observation_space=observation_space,
                         action_space=action_space,
                         device=device)
        self.model = model_cls(observation_space, action_space).to(self.device)
        self.model_target = deepcopy(self.model)
        self.gamma = gamma
        self.lam = lam
        self.clip_ratio = clip_ratio
        self.pi_lr = pi_lr
        self.vf_lr = vf_lr
        self.train_pi_iters = train_pi_iters
        self.train_v_iters = train_v_iters
        self.target_kl = target_kl
        self.pi_optimizer = Adam(self.model.actor.parameters(), lr=self.pi_lr, betas=(0.997, 0.997))
        self.vf_optimizer = Adam(itertools.chain(self.model.q1.parameters(), self.model.q2.parameters()), lr=self.vf_lr, betas=(0.997, 0.997))

    def get_actor(self):
        return self.model_nograd.actor

    def compute_returns_and_advantages(self, batch):
        o, a, r, o2, d, _ = batch

        with torch.no_grad():
            values = self.model.q1(o, a).cpu().numpy()
            next_values = self.model.q1(o2, a).cpu().numpy()

        advantages = []
        returns = []
        gae = 0
        for step in reversed(range(len(r))):
            delta = r[step] + self.gamma * next_values[step] * (1 - d[step]) - values[step]
            gae = delta + self.gamma * self.lam * (1 - d[step]) * gae
            advantages.insert(0, gae)
            returns.insert(0, gae + values[step])

        return torch.tensor(returns).to(self.device), torch.tensor(advantages).to(self.device)

    def train(self, batch):
        o, a, r, o2, d, _ = batch

        # Convert batch elements to tensors and move to the specified device
        o = tuple(item.clone().detach().to(self.device) for item in o)
        a = a.clone().detach().to(self.device)
        r = r.clone().detach().to(self.device)
        o2 = tuple(item.clone().detach().to(self.device) for item in o2)
        d = d.clone().detach().to(self.device)

        # Compute returns and advantages
        ret, adv = self.compute_returns_and_advantages((o, a, r, o2, d, _))

        # Compute old log probabilities
        with torch.no_grad():
            _, logp_old = self.model.actor(o, compute_logprob=True)

        # Policy loss
        for _ in range(self.train_pi_iters):
            pi, logp = self.model.actor(o, compute_logprob=True)
            ratio = torch.exp(logp - logp_old)
            clip_adv = torch.clamp(ratio, 1 - self.clip_ratio, 1 + self.clip_ratio) * adv
            loss_pi = -(torch.min(ratio * adv, clip_adv)).mean()

            self.pi_optimizer.zero_grad()
            loss_pi.backward()
            self.pi_optimizer.step()

        # Value function loss
        for _ in range(self.train_v_iters):
            q1 = self.model.q1(o, a)
            q2 = self.model.q2(o, a)
            loss_v = ((q1 - ret) ** 2).mean() + ((q2 - ret) ** 2).mean()
            self.vf_optimizer.zero_grad()
            loss_v.backward()
            self.vf_optimizer.step()

        ret_dict = dict(
            loss_actor=loss_pi.item(),
            loss_critic=loss_v.item(),
            kl_divergence=(logp_old - logp).mean().item()
        )
        return ret_dict


# Great! We are almost done.
# Now that our TrainingAgent class is defined, let us partially instantiate it.
# SAC has a few hyperparameters that we will need to tune if we want it to work as expected.
# The following have shown reasonable results in the past, using the full TrackMania environment.
# Note however that training a policy with SAC in this environment is a matter of several days!

training_agent_cls = partial(PPOTrainingAgent,
                             model_cls=VanillaCNNActorCritic,
                             gamma=0.99,
                             lam=0.95,
                             clip_ratio=0.2,
                             pi_lr=3e-4,
                             vf_lr=1e-3,
                             train_pi_iters=80,
                             train_v_iters=80,
                             target_kl=0.01)

training_cls = partial(
    TrainingOffline,
    env_cls=env_cls,
    memory_cls=memory_cls,
    training_agent_cls=training_agent_cls,
    epochs=epochs,
    rounds=rounds,
    steps=steps,
    update_buffer_interval=update_buffer_interval,
    update_model_interval=update_model_interval,
    max_training_steps_per_env_step=max_training_steps_per_env_step,
    start_training=start_training,
    device=device_trainer)

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('--server', action='store_true', help='launches the server')
    parser.add_argument('--trainer', action='store_true', help='launches the trainer')
    parser.add_argument('--worker', action='store_true', help='launches a rollout worker')
    parser.add_argument('--test', action='store_true', help='launches a rollout worker in standalone mode')
    args = parser.parse_args()

    if args.trainer:
        my_trainer = Trainer(training_cls=training_cls,
                             server_ip=server_ip_for_trainer,
                             server_port=server_port,
                             password=password,
                             security=security)
        my_trainer.run()
    elif args.worker or args.test:
        rw = RolloutWorker(env_cls=env_cls,
                           actor_module_cls=MyActorModule,
                           sample_compressor=sample_compressor,
                           device=device_worker,
                           server_ip=server_ip_for_worker,
                           server_port=server_port,
                           password=password,
                           security=security,
                           max_samples_per_episode=max_samples_per_episode,
                           obs_preprocessor=obs_preprocessor,
                           standalone=args.test)
        rw.run(test_episode_interval=10)
    elif args.server:
        import time
        serv = Server(port=server_port,
                      password=password,
                      security=security)
        while True:
            time.sleep(1.0)