%cd keras

from __future__ import division,print_function
import os, sys
import json
import numpy as np
from keras.utils.data_utils import get_file
import tensorflow as tf
import bcolz
import time

sys.path.append(os.getcwd())
from multi_gpu import make_parallel

from keras import backend as K
from keras.layers import Flatten, Dense, Input, Conv2D, MaxPooling2D, Dropout, BatchNormalization
from keras.models import Model
from keras.preprocessing import image
import keras
from keras.utils.np_utils import to_categorical
from keras.applications.imagenet_utils import _obtain_input_shape

sess = tf.Session(config=tf.ConfigProto(log_device_placement=True))

batch_size = 64
input_shape = (224, 224, 3)
img_input = Input(shape=input_shape)
# Block 1
x = Conv2D(64, (3, 3), activation='relu', padding='same', name='block1_conv1')(img_input)
x = Conv2D(64, (3, 3), activation='relu', padding='same', name='block1_conv2')(x)
x = MaxPooling2D((2, 2), strides=(2, 2), name='block1_pool')(x)

# Block 2
x = Conv2D(128, (3, 3), activation='relu', padding='same', name='block2_conv1')(x)
x = Conv2D(128, (3, 3), activation='relu', padding='same', name='block2_conv2')(x)
x = MaxPooling2D((2, 2), strides=(2, 2), name='block2_pool')(x)

# Block 3
x = Conv2D(256, (3, 3), activation='relu', padding='same', name='block3_conv1')(x)
x = Conv2D(256, (3, 3), activation='relu', padding='same', name='block3_conv2')(x)
x = Conv2D(256, (3, 3), activation='relu', padding='same', name='block3_conv3')(x)
x = MaxPooling2D((2, 2), strides=(2, 2), name='block3_pool')(x)

# Block 4
x = Conv2D(512, (3, 3), activation='relu', padding='same', name='block4_conv1')(x)
x = Conv2D(512, (3, 3), activation='relu', padding='same', name='block4_conv2')(x)
x = Conv2D(512, (3, 3), activation='relu', padding='same', name='block4_conv3')(x)
x = MaxPooling2D((2, 2), strides=(2, 2), name='block4_pool')(x)

# Block 5
x = Conv2D(512, (3, 3), activation='relu', padding='same', name='block5_conv1')(x)
x = Conv2D(512, (3, 3), activation='relu', padding='same', name='block5_conv2')(x)
x = Conv2D(512, (3, 3), activation='relu', padding='same', name='block5_conv3')(x)
x = MaxPooling2D((2, 2), strides=(2, 2), name='block5_pool')(x)

# dense
x = Flatten(name='flatten')(x)
x = Dense(4096, activation='relu', name='fc1')(x)
x = Dense(4096, activation='relu', name='fc2')(x)
x = Dense(1000, activation='softmax', name='predictions')(x)
model_full = Model(img_input, x, name='vgg16_full')

WEIGHTS_PATH = 'https://github.com/fchollet/deep-learning-models/releases/download/v0.1/vgg16_weights_tf_dim_ordering_tf_kernels.h5'
weights_path = get_file('vgg16_weights_tf_dim_ordering_tf_kernels.h5', WEIGHTS_PATH, cache_subdir='models')
model_full.load_weights(weights_path)

last_conv_idx = [i for i,l in enumerate(model_full.layers) if type(l) is Conv2D][-1]
conv_layers = model_full.layers[:last_conv_idx + 2]  # max pooling is last layer

last_conv_layer = conv_layers[-1]
model = Model(img_input, last_conv_layer.get_output_at(0), name='vgg16_conv')

# this function simply copies model to multiple gpus and splits up minibatches
# across the gpus
num_gpus = 2
if num_gpus > 1:
  model = make_parallel(model, num_gpus)

path = '/home/cdsw/train_data/256_ObjectCategories/'
# Do not shuffle the data! You'll lose the label ordering
generator = image.ImageDataGenerator()
batches = generator.flow_from_directory(path + 'train', target_size=(224, 224), class_mode='categorical', shuffle=False, batch_size=batch_size)
val_batches = generator.flow_from_directory(path + 'valid', target_size=(224, 224), class_mode='categorical', shuffle=False, batch_size=batch_size)
test_batches = generator.flow_from_directory(path + 'test', target_size=(224, 224), class_mode='categorical', shuffle=False, batch_size=batch_size)
(val_classes, trn_classes, val_labels, trn_labels) = \
(val_batches.classes, batches.classes, to_categorical(val_batches.classes), to_categorical(batches.classes))
test_classes, test_labels = test_batches.classes, to_categorical(test_batches.classes)

def featurize_and_save(phase, batches, labels):
  t0 = time.time()
  conv_feat = model.predict_generator(batches, int(batches.samples / batch_size) + 1)
  c = bcolz.carray(conv_feat, rootdir='./data/conv_%s_feat.dat' % phase)
  n = c.shape[0]
  c.flush()
  c_label = bcolz.carray(labels, rootdir='./data/conv_%s_feat_label.dat' % phase)
  c_label.flush()
  t1 = time.time()
  print("Featurized %d images in %0.1f seconds." % (n, t1 - t0))

featurize_and_save("valid", val_batches, val_labels)
featurize_and_save("train", batches, trn_labels)
featurize_and_save("test", test_batches, test_labels)