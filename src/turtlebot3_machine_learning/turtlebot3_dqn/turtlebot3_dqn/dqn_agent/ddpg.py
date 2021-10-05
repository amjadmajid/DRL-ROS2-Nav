import numpy
from keras.models import Model
from keras.layers import Dense, Input
from keras.layers.merge import Concatenate
from keras.optimizers import Adam
import keras.backend as K
import tensorflow as tf
import random

import os.path
import timeit
import csv
import math
import time
import matplotlib.pyplot as plt


class Actor:

    def __init__(self, state_size):
        self.state_size = state_size

    def build_model(self):
        state_input = Input(shape=self.state_size)
        h1 = Dense(500, activation='relu')(state_input)
        h2 = Dense(500, activation='relu')(h1)
        h3 = Dense(500, activation='relu')(h2)
        delta_theta = Dense(1, activation='tanh')(h3)
        # sigmoid makes the output to be range [0, 1]
        speed = Dense(1, activation='sigmoid')(h3)

        output = Concatenate()([delta_theta, speed])
        model = Model(input=state_input, output=output)
        adam = Adam(lr=0.0001)
        model.compile(loss="mse", optimizer=adam)
        model.summary()
        self.model = model

    def forward_pass(self, states):
        # TODO: use predict on batch?
        return self.model(states)

    def train_actor(self):
        print("test")

    def get_action(self, state, epsilon):
        action = self.model(state.reshape(1, len(state)))
        if numpy.random.random() < epsilon:
            action[0][0] = action[0][0] + (numpy.random.random()-0.5)*0.4
            action[0][1] = action[0][1] + numpy.random.random()*0.4
            return action
        else:
            action[0][0] = action[0][0]
            action[0][1] = action[0][1]
            return action

    def train_critic_actor(self, samples):

        states, actions, rewards, states_new, dones = stack_samples(
            samples)
        target_actions = self.target_actor_model.predict(states_new)
        future_rewards = self.target_critic_model.predict(
            [states_new, target_actions])
        rewards = rewards + self.gamma * future_rewards * (1 - dones)

        # print("cur_states is %s", cur_states)

        # evaluation = self.critic_model.fit([cur_states, actions], rewards, verbose=0, sample_weight=_sample_weight)
        evaluation = self.critic_model.fit(
            [states, actions], rewards, verbose=0)
        # print('\nhistory dict:', evaluation.history)

        # 5, train actor based on weights
        predicted_actions = self.actor_model.predict(states)
        grads = self.sess.run(self.critic_grads, feed_dict={
            self.critic_state_input:  states,
            self.critic_action_input: predicted_actions
        })[0]

        self.sess.run(self.optimize, feed_dict={
            self.actor_state_input: states,
            self.actor_critic_grad: grads
        })
        # print("grads*weights is %s", grads)

    def read_Q_values(self, cur_states, actions):
        critic_values = self.critic_model.predict([cur_states, actions])
        return critic_values

    def train(self):
        batch_size = self.batch_size
        if len(self.memory) < batch_size:  # batch_size:
            return
        samples = random.sample(self.memory, batch_size)
        # samples = self.memory.sample(1, batch_size)
        self.samples = samples
        # print("samples is %s", samples)
        # print("samples [1] is %s", samples[1])
        print("length of memory is %s", len(self.memory))
        # print("samples shape is %s", samples.shape)
        self._train_critic_actor(samples)

    # ========================================================================= #
    #                         Target Model Updating                             #
    # ========================================================================= #

    def update_actor_target(self):
        actor_model_weights = self.actor_model.get_weights()
        actor_target_weights = self.target_actor_model.get_weights()

        for i in range(len(actor_target_weights)):
            actor_target_weights[i] = actor_model_weights[i] * \
                self.tau + actor_target_weights[i]*(1-self.tau)
        self.target_actor_model.set_weights(actor_target_weights)

    def update_critic_target(self):
        critic_model_weights = self.critic_model.get_weights()
        critic_target_weights = self.target_critic_model.get_weights()

        for i in range(len(critic_target_weights)):
            critic_target_weights[i] = critic_model_weights[i] * \
                self.tau + critic_target_weights[i]*(1-self.tau)
        self.target_critic_model.set_weights(critic_target_weights)

    def update_target(self):
        self._update_actor_target()
        self._update_critic_target()


class Critic:

    def __init__(self, state_size, action_size):
        self.state_size = state_size
        self.action_size = action_size

    def build_model(self):
        state_input = Input(shape=self.state_size)
        state_h1 = Dense(500, activation='relu')(state_input)

        action_input = Input(shape=self.action_size)
        action_h1 = Dense(500)(action_input)

        merged = Concatenate()([state_h1, action_h1])
        merged_h1 = Dense(500, activation='relu')(merged)
        merged_h2 = Dense(500, activation='relu')(merged_h1)
        output = Dense(1, activation='linear')(merged_h2)
        model = Model(input=[state_input, action_input], output=output)

        adam = Adam(lr=0.0001)
        model.compile(loss="mse", optimizer=adam)
        model.summary()
        self.model = model

    def forward_pass(self, states, actions):
        return self.model([states, actions])

    def train_critic(self):
