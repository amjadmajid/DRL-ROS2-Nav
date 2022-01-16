#!/usr/bin/env python3
#
# Copyright 2019 ROBOTIS CO., LTD.
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
#
# Authors: Ryan Shim, Gilbert

import copy
import numpy
import os
import sys
import time

import torch
import torch.nn.functional as F

from .ddpg import Critic, Actor
from .replaybuffer import ReplayBuffer
from . import storagemanager as sm
from .ounoise import OUNoise

from turtlebot3_msgs.srv import Ddpg
from turtlebot3_msgs.srv import Goal
from std_srvs.srv import Empty

import rclpy
from rclpy.node import Node

import matplotlib.pyplot as plt

import tracemalloc

# Constants
ACTION_LINEAR_MAX = 0.22
ACTION_ANGULAR_MAX = 2.0

INDEX_LIN = 0
INDEX_ANG = 1

PLOT_INTERVAL = 10


class DDPGAgent(Node):
    def __init__(self, stage, agent, episode):
        super().__init__('ddpg_agent')

        tracemalloc.start()

        self.stage = int(stage)
        # Specify which model and episode to load from models_directory or Change to False for new session
        self.load_session = agent  # example: 'ddpg_0'
        self.load_episode = episode if self.load_session else 0

        # ===================================================================== #
        #                       parameter initalization                         #
        # ===================================================================== #

        # 36 laser readings, distance to goal, angle to goal, previous linear action, previous angular action
        self.state_size = 14
        self.action_size = 2
        self.episode_size = 10000

        # General hyperparameters
        self.discount_factor = 0.90
        self.learning_rate = 0.0001
        self.batch_size = 128

        # DDPG hyperparameters
        self.tau = 0.001

        # Replay memory
        self.memory_size = 100000
        self.memory = ReplayBuffer(self.memory_size)

        # metrics
        self.loss_critic_sum = 0.0
        self.loss_actor_sum = 0.0

        # logging
        self.rewards_data = []
        self.avg_critic_loss_data = []
        self.avg_actor_loss_data = []

        # ===================================================================== #
        #                          GPU initalization                            #
        # ===================================================================== #

        print("gpu torch available: ", torch.cuda.is_available())
        if (torch.cuda.is_available()):
            print("device name: ", torch.cuda.get_device_name(0))

        # ===================================================================== #
        #                        Models initialization                          #
        # ===================================================================== #

        self.actor = Actor("actor", self.state_size, self.action_size, ACTION_LINEAR_MAX, ACTION_ANGULAR_MAX)
        self.target_actor = Actor("target_actor", self.state_size, self.action_size, ACTION_LINEAR_MAX, ACTION_ANGULAR_MAX)
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), self.learning_rate)

        self.critic = Critic("critic", self.state_size, self.action_size)
        self.target_critic = Critic("target_critic", self.state_size, self.action_size)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(), self.learning_rate)

        self.update_network_parameters(1)

        self.actor_noise = OUNoise(self.action_size, max_sigma=0.1, min_sigma=0.1, decay_period=8000000)

        # ===================================================================== #
        #                             Model loading                             #
        # ===================================================================== #

        # Directory where your models will be stored and loaded from
        models_directory = (os.path.dirname(os.path.realpath(__file__))).replace(
            'install/turtlebot3_ddpg/lib/python3.8/site-packages/turtlebot3_ddpg/ddpg_agent',
            'src/turtlebot3_ddpg/model')

        # Specify whether model is being trained or only evaluated
        self.training = True
        self.record_results = True
        # store model every N episodes
        self.store_interval = 100

        if self.load_session:
            self.session_dir = os.path.join(models_directory, self.load_session)
            sm.load_session(self, self.session_dir, self.load_episode)
        else:
            self.session_dir = sm.new_session_dir(models_directory)

        # File where results per episode are written
        if self.record_results:
            self.results_file = open(os.path.join(self.session_dir, time.strftime("%Y%m%d-%H%M%S") + '.txt'), 'w+')

        # ===================================================================== #
        #                             Start Process                             #
        # ===================================================================== #

        self.ddpg_com_client = self.create_client(Ddpg, 'ddpg_com')
        self.goal_com_client = self.create_client(Goal, 'goal_com')
        self.process()

    # ===================================================================== #
    #                           Class functions                             #
    # ===================================================================== #

    def get_action(self, state, step):
        state = numpy.asarray(state, numpy.float32)
        state = torch.from_numpy(state)
        action = self.actor.forward(state).detach()
        action = action.data.numpy()
        action = action.tolist()
        N = copy.deepcopy(self.actor_noise.get_noise(t=step))
        N[0] = N[0]*ACTION_LINEAR_MAX/2
        N[1] = N[1]*ACTION_ANGULAR_MAX
        action[0] = numpy.clip(action[0] + N[0], 0.0, ACTION_LINEAR_MAX)
        action[1] = numpy.clip(action[1] + N[1], -ACTION_ANGULAR_MAX, ACTION_ANGULAR_MAX)
        return action

    def update_network_parameters(self, tau):
        # update target actor
        for target_param, param in zip(self.target_actor.parameters(), self.actor.parameters()):
            target_param.data.copy_(target_param.data*(1.0 - tau) + param.data*tau)
        # update target critic
        for target_param, param in zip(self.target_critic.parameters(), self.critic.parameters()):
            target_param.data.copy_(target_param.data*(1.0 - tau) + param.data*tau)

    def train(self):
        # Not enough samples have been collected yet
        if self.memory.get_length() < self.batch_size:
            return 0, 0

        return 0, 0

        s_sample, a_sample, r_sample, new_s_sample, done_sample = self.memory.sample(self.batch_size)

        s_sample = torch.from_numpy(s_sample)
        a_sample = torch.from_numpy(a_sample)
        r_sample = torch.from_numpy(r_sample)
        new_s_sample = torch.from_numpy(new_s_sample)
        done_sample = torch.from_numpy(done_sample)

        # optimize critic
        a_target = self.target_actor.forward(new_s_sample).detach()
        next_value = torch.squeeze(self.target_critic.forward(new_s_sample, a_target).detach())
        # y_exp = r _ gamma*Q'(s', P'(s'))
        y_expected = r_sample + (1 - done_sample)*self.discount_factor*next_value
        # y_pred = Q(s,a)
        y_predicted = torch.squeeze(self.critic.forward(s_sample, a_sample))
        self.qvalue = y_predicted.detach()
        # print(torch.max(self.qvalue))

        # return 0, 0

        loss_critic = F.smooth_l1_loss(y_predicted, y_expected)
        self.loss_critic_sum += loss_critic.detach()
        self.critic_optimizer.zero_grad()
        loss_critic.backward()
        # torch.nn.utils.clip_grad_norm_(model.parameters(), args.clip)
        self.critic_optimizer.step()

        # optimize actor
        pred_a_sample = self.actor.forward(s_sample)
        loss_actor = -1*torch.sum(self.critic.forward(s_sample, pred_a_sample))
        self.loss_actor_sum += loss_actor.detach()

        self.actor_optimizer.zero_grad()
        loss_actor.backward()
        self.actor_optimizer.step()

        # Soft update all target networks
        self.update_network_parameters(self.tau)

    def step(self, action, previous_action):
        req = Ddpg.Request()
        req.action = action
        req.previous_action = previous_action

        while not self.ddpg_com_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('env step service not available, waiting again...')
        future = self.ddpg_com_client.call_async(req)

        while rclpy.ok():
            rclpy.spin_once(self)
            if future.done():
                if future.result() is not None:
                    res = future.result()
                    return res.state, res.reward, res.done, res.success
                else:
                    self.get_logger().error(
                        'Exception while calling service: {0}'.format(future.exception()))
                    print("ERROR getting ddpg service response!")

    def get_goal_status(self):
        req = Goal.Request()
        while not self.goal_com_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('new goal service not available, waiting again...')
        future = self.goal_com_client.call_async(req)

        while rclpy.ok():
            rclpy.spin_once(self)
            if future.done():
                if future.result() is not None:
                    res = future.result()
                    return res.new_goal
                else:
                    self.get_logger().error(
                        'Exception while calling service: {0}'.format(future.exception()))
                    print("ERROR getting new_goal service response!")

    def update_plots(self, episode, reward, critic_loss, actor_loss):
        # plot 1:
        xaxis = numpy.array(range(episode))
        x = xaxis
        y = reward
        print(x)
        print(y)
        plt.subplot(2, 2, 1)
        plt.gca().set_title('reward')
        plt.plot(x, y)

        # plot 2:
        x = xaxis
        y = numpy.array(critic_loss)

        plt.subplot(2, 2, 2)
        plt.gca().set_title('avg critic loss over episode')
        plt.plot(x, y)

        # plot 3:
        x = xaxis
        y = numpy.array(actor_loss)

        plt.subplot(2, 2, 3)
        plt.gca().set_title('avg actor loss over episode')
        plt.plot(x, y)

        # plot 4:
        count = int(episode / PLOT_INTERVAL)
        if count > 0:
            x = numpy.array(range(PLOT_INTERVAL, episode+1, PLOT_INTERVAL))
            averages = list()
            for i in range(count):
                avg_sum = 0
                for j in range(PLOT_INTERVAL):
                    avg_sum += reward[i * PLOT_INTERVAL + j]
                averages.append(avg_sum / PLOT_INTERVAL)
            y = numpy.array(averages)
            plt.subplot(2, 2, 4)
            plt.gca().set_title('avg reward over 10 episodes')
            plt.plot(x, y)

        plt.draw()
        plt.pause(0.001)
        plt.show()

    def process(self):
        success_count = 0

        if self.record_results:
            self.results_file.write(
                "episode, reward, success, duration, n_steps, success_count, memory length, avg_critic_loss, avg_actor_loss\n")

        # for episode in range(self.load_episode+1, self.episode_size):
        episode = 0

        plt.figure()
        plt.axis([-50, 50, 0, 10000])
        plt.ion()
        plt.show()

        while (True):
            episode += 1
            past_action = [0.0, 0.0]
            state, _, _, _ = self.step([], past_action)
            next_state = list()
            done = False
            step = 0
            reward_sum = 0.0
            time.sleep(1.0)
            episode_start = time.time()
            self.loss_critic_sum = 0.0
            self.loss_actor_sum = 0.0

            while not done:
                # Get action, take step, learn
                action = self.get_action(state, step)
                next_state, reward, done, success = self.step(action, past_action)
                past_action = copy.deepcopy(action)
                reward_sum += reward

                if step > 1:
                    self.memory.add_sample(state, action, reward, next_state, done)
                    if self.training == True:
                        self.train()

                    if done:
                        avg_critic_loss = self.loss_critic_sum / step
                        avg_actor_loss = self.loss_actor_sum / step
                        episode_duration = time.time() - episode_start
                        print(f"Episode: {episode} score: {reward_sum} success: {success}\
                            n_steps: {step} memory length: {self.memory.get_length()} episode duration: {episode_duration}")
                        self.results_file.write(f"{episode}, {reward_sum}, {success}, {episode_duration}, \
                            {step}, {success_count}, {self.memory.get_length()}, {avg_critic_loss}, {avg_actor_loss}")

                        # self.rewards_data.append(reward_sum)
                        # self.avg_critic_loss_data.append(avg_critic_loss)
                        # self.avg_actor_loss_data.append(avg_actor_loss)
                        # self.update_plots(episode, self.rewards_data, self.avg_critic_loss_data, self.avg_actor_loss_data)

                        snapshot = tracemalloc.take_snapshot()
                        top_stats = snapshot.statistics('lineno')

                        print(f"[ Top 10 (out of {len(top_stats)})]")
                        for stat in top_stats[:10]:
                            print(stat)

                        if self.training != True:
                            print("Waiting for new goal...")
                            while(self.get_goal_status() == False):
                                time.sleep(1.0)

                state = next_state
                step += 1
                time.sleep(0.01)  # While loop rate

            if (self.training == True):
                if (episode % self.store_interval == 0) or (episode == 1):
                    sm.save_session(self, self.session_dir, episode)


def main(args=sys.argv[1:]):
    rclpy.init(args=args)
    ddpg_agent = DDPGAgent(args[0], args[1], args[2])
    rclpy.spin(ddpg_agent)

    ddpg_agent.destroy()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
