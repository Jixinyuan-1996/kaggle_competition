
# coding: utf-8

# # About
# Since I am new to learning from image segmentation and kaggle in general I want to share my noteook.
# I saw it is similar to others as it uses the U-net approach. I want to share it anyway because:
# 
# - As said, the field is new to me so I am open to suggestions.
# - It visualizes some of the steps, e.g. scaling, to learn if the methods do what I expect which might be useful to others (I call them sanity checks).
# - Added stratification by the amount of salt contained in the image.
# - Added augmentation by flipping the images along the y axes (thanks to the forum for clarification).
# - Added dropout to the model which seems to improve performance.

# In[ ]:


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import pandas as pd

from random import randint

import matplotlib.pyplot as plt
plt.style.use('seaborn-white')
import seaborn as sns
sns.set_style("white")

from sklearn.model_selection import train_test_split

from skimage.transform import resize

from keras.preprocessing.image import load_img
from keras import Model
from keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from keras.models import load_model
from keras.optimizers import Adam
from keras.utils.vis_utils import plot_model
from keras.preprocessing.image import ImageDataGenerator
from keras.layers import Input, Conv2D, Conv2DTranspose, MaxPooling2D, concatenate, Dropout

from tqdm import tqdm_notebook


# # Params and helpers

# In[ ]:


img_size_ori = 101
img_size_target = 128

def upsample(img):
    if img_size_ori == img_size_target:
        return img
    return resize(img, (img_size_target, img_size_target), mode='constant', preserve_range=True)
    #res = np.zeros((img_size_target, img_size_target), dtype=img.dtype)
    #res[:img_size_ori, :img_size_ori] = img
    #return res
def downsample(img):
    if img_size_ori == img_size_target:
        return img
    return resize(img, (img_size_ori, img_size_ori), mode='constant', preserve_range=True)
    #return img[:img_size_ori, :img_size_ori]
def cov_to_class(val):
    for i in range(0, 11):
        if val * 10 <= i :
            return i
def build_model(input_layer, start_neurons):
    # 128 -> 64
    conv1 = Conv2D(start_neurons * 1, (3, 3), activation="relu", padding="same")(input_layer)
    conv1 = Conv2D(start_neurons * 1, (3, 3), activation="relu", padding="same")(conv1)
    pool1 = MaxPooling2D((2, 2))(conv1)
    pool1 = Dropout(0.25)(pool1)

    # 64 -> 32
    conv2 = Conv2D(start_neurons * 2, (3, 3), activation="relu", padding="same")(pool1)
    conv2 = Conv2D(start_neurons * 2, (3, 3), activation="relu", padding="same")(conv2)
    pool2 = MaxPooling2D((2, 2))(conv2)
    pool2 = Dropout(0.5)(pool2)

    # 32 -> 16
    conv3 = Conv2D(start_neurons * 4, (3, 3), activation="relu", padding="same")(pool2)
    conv3 = Conv2D(start_neurons * 4, (3, 3), activation="relu", padding="same")(conv3)
    pool3 = MaxPooling2D((2, 2))(conv3)
    pool3 = Dropout(0.5)(pool3)

    # 16 -> 8
    conv4 = Conv2D(start_neurons * 8, (3, 3), activation="relu", padding="same")(pool3)
    conv4 = Conv2D(start_neurons * 8, (3, 3), activation="relu", padding="same")(conv4)
    pool4 = MaxPooling2D((2, 2))(conv4)
    pool4 = Dropout(0.5)(pool4)

    # Middle
    convm = Conv2D(start_neurons * 16, (3, 3), activation="relu", padding="same")(pool4)
    convm = Conv2D(start_neurons * 16, (3, 3), activation="relu", padding="same")(convm)

    # 8 -> 16
    deconv4 = Conv2DTranspose(start_neurons * 8, (3, 3), strides=(2, 2), padding="same")(convm)
    uconv4 = concatenate([deconv4, conv4])
    uconv4 = Dropout(0.5)(uconv4)
    uconv4 = Conv2D(start_neurons * 8, (3, 3), activation="relu", padding="same")(uconv4)
    uconv4 = Conv2D(start_neurons * 8, (3, 3), activation="relu", padding="same")(uconv4)

    # 16 -> 32
    deconv3 = Conv2DTranspose(start_neurons * 4, (3, 3), strides=(2, 2), padding="same")(uconv4)
    uconv3 = concatenate([deconv3, conv3])
    uconv3 = Dropout(0.5)(uconv3)
    uconv3 = Conv2D(start_neurons * 4, (3, 3), activation="relu", padding="same")(uconv3)
    uconv3 = Conv2D(start_neurons * 4, (3, 3), activation="relu", padding="same")(uconv3)

    # 32 -> 64
    deconv2 = Conv2DTranspose(start_neurons * 2, (3, 3), strides=(2, 2), padding="same")(uconv3)
    uconv2 = concatenate([deconv2, conv2])
    uconv2 = Dropout(0.5)(uconv2)
    uconv2 = Conv2D(start_neurons * 2, (3, 3), activation="relu", padding="same")(uconv2)
    uconv2 = Conv2D(start_neurons * 2, (3, 3), activation="relu", padding="same")(uconv2)

    # 64 -> 128
    deconv1 = Conv2DTranspose(start_neurons * 1, (3, 3), strides=(2, 2), padding="same")(uconv2)
    uconv1 = concatenate([deconv1, conv1])
    uconv1 = Dropout(0.5)(uconv1)
    uconv1 = Conv2D(start_neurons * 1, (3, 3), activation="relu", padding="same")(uconv1)
    uconv1 = Conv2D(start_neurons * 1, (3, 3), activation="relu", padding="same")(uconv1)

    uncov1 = Dropout(0.5)(uconv1)
    output_layer = Conv2D(1, (1,1), padding="same", activation="sigmoid")(uconv1)
    
    return output_layer
# src: https://www.kaggle.com/aglotero/another-iou-metric
def iou_metric(y_true_in, y_pred_in, print_table=False):
    labels = y_true_in
    y_pred = y_pred_in
    
    true_objects = 2
    pred_objects = 2

    intersection = np.histogram2d(labels.flatten(), y_pred.flatten(), bins=(true_objects, pred_objects))[0]

    # Compute areas (needed for finding the union between all objects)
    area_true = np.histogram(labels, bins = true_objects)[0]
    area_pred = np.histogram(y_pred, bins = pred_objects)[0]
    area_true = np.expand_dims(area_true, -1)
    area_pred = np.expand_dims(area_pred, 0)

    # Compute union
    union = area_true + area_pred - intersection

    # Exclude background from the analysis
    intersection = intersection[1:,1:]
    union = union[1:,1:]
    union[union == 0] = 1e-9

    # Compute the intersection over union
    iou = intersection / union

    # Precision helper function
    def precision_at(threshold, iou):
        matches = iou > threshold
        true_positives = np.sum(matches, axis=1) == 1   # Correct objects
        false_positives = np.sum(matches, axis=0) == 0  # Missed objects
        false_negatives = np.sum(matches, axis=1) == 0  # Extra objects
        tp, fp, fn = np.sum(true_positives), np.sum(false_positives), np.sum(false_negatives)
        return tp, fp, fn

    # Loop over IoU thresholds
    prec = []
    if print_table:
        print("Thresh\tTP\tFP\tFN\tPrec.")
    for t in np.arange(0.5, 1.0, 0.05):
        tp, fp, fn = precision_at(t, iou)
        if (tp + fp + fn) > 0:
            p = tp / (tp + fp + fn)
        else:
            p = 0
        if print_table:
            print("{:1.3f}\t{}\t{}\t{}\t{:1.3f}".format(t, tp, fp, fn, p))
        prec.append(p)
    
    if print_table:
        print("AP\t-\t-\t-\t{:1.3f}".format(np.mean(prec)))
    return np.mean(prec)

def iou_metric_batch(y_true_in, y_pred_in):
    batch_size = y_true_in.shape[0]
    metric = []
    for batch in range(batch_size):
        value = iou_metric(y_true_in[batch], y_pred_in[batch])
        metric.append(value)
    return np.mean(metric)
# Source https://www.kaggle.com/bguberfain/unet-with-depth
def RLenc(img, order='F', format=True):
    """
    img is binary mask image, shape (r,c)
    order is down-then-right, i.e. Fortran
    format determines if the order needs to be preformatted (according to submission rules) or not

    returns run length as an array or string (if format is True)
    """
    bytes = img.reshape(img.shape[0] * img.shape[1], order=order)
    runs = []  ## list of run lengths
    r = 0  ## the current run length
    pos = 1  ## count starts from 1 per WK
    for c in bytes:
        if (c == 0):
            if r != 0:
                runs.append((pos, r))
                pos += r
                r = 0
            pos += 1
        else:
            r += 1

    # if last run is unsaved (i.e. data ends with 1)
    if r != 0:
        runs.append((pos, r))
        pos += r
        r = 0

    if format:
        z = ''

        for rr in runs:
            z += '{} {} '.format(rr[0], rr[1])
        return z[:-1]
    else:
        return runs
    
    
#***************crf函数部分********************

import os
import sys

import numpy as np
import imageio
# import scipy as scp
# import scipy.misc

import argparse

import logging
import time

from convcrf import convcrf

import torch
from torch.autograd import Variable

from utils import pascal_visualizer as vis
from utils import synthetic

try:
    import matplotlib.pyplot as plt
    figure = plt.figure()
    matplotlib = True
    plt.close(figure)
except:
    matplotlib = False
    pass

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s',
                    level=logging.INFO,
                    stream=sys.stdout)


def do_crf_inference(image, unary, args):

    if args.pyinn or not hasattr(torch.nn.functional, 'unfold'):
        # pytorch 0.3 or older requires pyinn.
        args.pyinn = True
        # Cheap and easy trick to make sure that pyinn is loadable.
        import pyinn

    # get basic hyperparameters
    num_classes = unary.shape[2]
    shape = image.shape[0:2]
    config = convcrf.default_conf
    config['filter_size'] = 7
    config['pyinn'] = args.pyinn

    if args.normalize:
        # Warning, applying image normalization affects CRF computation.
        # The parameter 'col_feats::schan' needs to be adapted.

        # Normalize image range
        #     This changes the image features and influences CRF output
        image = image / 255
        # mean substraction
        #    CRF is invariant to mean subtraction, output is NOT affected
        image = image - 0.5
        # std normalization
        #       Affect CRF computation
        image = image / 0.3

        # schan = 0.1 is a good starting value for normalized images.
        # The relation is f_i = image * schan
        config['col_feats']['schan'] = 0.1

    # make input pytorch compatible
    # Add batch dimension to image: [1, 1, height, width]
    image = image.reshape([1, 1, shape[0], shape[1]])
    img_var = Variable(torch.Tensor(image))#.cuda()

    unary = unary.transpose(2, 0, 1)  # shape: [3, hight, width]
    # Add batch dimension to unary: [1, 21, height, width]
    unary = unary.reshape([1, num_classes, shape[0], shape[1]])
    unary_var = Variable(torch.Tensor(unary))# .cuda()

    logging.info("Build ConvCRF.")
    ##
    # Create CRF module
    gausscrf = convcrf.GaussCRF(conf=config, shape=shape, nclasses=num_classes)
    # Cuda computation is required.
    # A CPU implementation of our message passing is not provided.
    #gausscrf()#.cuda()

    logging.info("Start Computation.")
    # Perform CRF inference
    prediction = gausscrf.forward(unary=unary_var, img=img_var)

    if args.nospeed:
        # Evaluate inference speed
        logging.info("Doing speed evaluation.")
        start_time = time.time()
        for i in range(10):
            # Running ConvCRF 10 times and average total time
            pred = gausscrf.forward(unary=unary_var, img=img_var)

        pred.cpu()  # wait for all GPU computations to finish

        duration = (time.time() - start_time) * 1000 / 10

        logging.info("Finished running 10 predictions.")
        logging.info("Avg. Computation time: {} ms".format(duration))

    return prediction.data.cpu().numpy()


def plot_results(image, unary, prediction, label, args):

    logging.info("Plot results.")

    # Create visualizer
    myvis = vis.PascalVisualizer()

    # Transform id image to coloured labels
    coloured_label = myvis.id2color(id_image=label)

    unary_hard = np.argmax(unary, axis=2)
    coloured_unary = myvis.id2color(id_image=unary_hard)

    prediction = prediction[0]  # Remove Batch dimension
    prediction_hard = np.argmax(prediction, axis=0)
    coloured_crf = myvis.id2color(id_image=prediction_hard)

    if matplotlib:
        # Plot results using matplotlib
        figure = plt.figure()
        figure.tight_layout()

        # Plot parameters
        num_rows = 2
        num_cols = 2

        ax = figure.add_subplot(num_rows, num_cols, 1)
        # img_name = os.path.basename(args.image)
        ax.set_title('Image ')
        ax.axis('off')
        ax.imshow(np.array(image/255).squeeze(), cmap="Greys")

        ax = figure.add_subplot(num_rows, num_cols, 2)
        ax.set_title('Label')
        ax.axis('off')
        ax.imshow(coloured_label.astype(np.uint8))

        ax = figure.add_subplot(num_rows, num_cols, 3)
        ax.set_title('Unary')
        ax.axis('off')
        ax.imshow(coloured_unary.astype(np.uint8))

        ax = figure.add_subplot(num_rows, num_cols, 4)
        ax.set_title('CRF Output')
        ax.axis('off')
        ax.imshow(coloured_crf.astype(np.uint8))

        plt.show()
    else:
        if args.output is None:
            args.output = "out.png"

        logging.warning("Matplotlib not found.")
        logging.info("Saving output to {} instead".format(args.output))

    if args.output is not None:
        # Save results to disk
        out_img = np.concatenate(
            (image, coloured_label, coloured_unary, coloured_crf),
            axis=1)

        imageio.imwrite(args.output, out_img.astype(np.uint8))

        logging.info("Plot has been saved to {}".format(args.output))

    return


def get_parser():
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
    parser = ArgumentParser(description=__doc__,
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument("--image", type=str,default=False,
                        help="input image")
    
    parser.add_argument("--label", type=str,default=False,
                        help="Label file.")
    
    parser.add_argument("--gpu", type=str, default=False,
                        help="which gpu to use")

    parser.add_argument('--output', type=str,
                        help="Optionally save output as img.")

    parser.add_argument('--nospeed', action='store_false',
                        help="Skip speed evaluation.")

    parser.add_argument('--normalize', action='store_true',
                        help="Normalize input image before inference.")

    parser.add_argument('--pyinn', action='store_true',
                        help="Use pyinn based Cuda implementation"
                             "for message passing.")

    # parser.add_argument('--compare', action='store_true')
    # parser.add_argument('--embed', action='store_true')

    # args = parser.parse_args()

    return parser               
#=====================================================begin======================================================



if __name__ == '__main__':
    
  
    # In[ ]:Loading of training/testing ids and depths
    
      # Reading the training data and the depths, store them in a DataFrame. Also create a test DataFrame with entries from depth not in train.
    
    train_df = pd.read_csv("input/train.csv", index_col="id", usecols=[0])
    depths_df = pd.read_csv("input/depths.csv", index_col="id")
    train_df = train_df.join(depths_df)
    test_df = depths_df[~depths_df.index.isin(train_df.index)]
    
    
    # In[ ]: Read images and masks
      
      # Load the images and masks into the DataFrame and divide the pixel values by 255.
    
    train_df["images"] = [np.array(load_img("input/train/images/{}.png".format(idx), grayscale=True)) / 255 for idx in tqdm_notebook(train_df.index)]
    train_df["masks"] = [np.array(load_img("input/train/masks/{}.png".format(idx), grayscale=True)) / 255 for idx in tqdm_notebook(train_df.index)]
 
    
    # In[ ]:Calculating the salt coverage and salt coverage classes
    
       # Counting the number of salt pixels in the masks and dividing them by the image size. Also create 11 coverage classes, -0.1 having no salt at all to 1.0 being salt only.
    
    train_df["coverage"] = train_df.masks.map(np.sum) / pow(img_size_ori, 2)
    train_df["coverage_class"] = train_df.coverage.map(cov_to_class)
    
    
    # In[ ]: Plotting the distribution of coverages and coverage classes, and the class against the raw coverage.
    
    fig, axs = plt.subplots(1, 2, figsize=(15,5))
    sns.distplot(train_df.coverage, kde=False, ax=axs[0])
    sns.distplot(train_df.coverage_class, bins=10, kde=False, ax=axs[1])
    plt.suptitle("Salt coverage")
    axs[0].set_xlabel("Coverage")
    axs[1].set_xlabel("Coverage class")
    plt.scatter(train_df.coverage, train_df.coverage_class)
    plt.xlabel("Coverage")
    plt.ylabel("Coverage class")
   
    # In[ ]: Plotting the depth distributions
       
        # Separatelty plotting the depth distributions for the training and the testing data.
    
    sns.distplot(train_df.z, label="Train")
    sns.distplot(test_df.z, label="Test")
    plt.legend()
    plt.title("Depth distribution")
    
    
    # In[ ]:Show some example images
    
    
    max_images = 60
    grid_width = 15
    grid_height = int(max_images / grid_width)
    fig, axs = plt.subplots(grid_height, grid_width, figsize=(grid_width, grid_height))
    for i, idx in enumerate(train_df.index[:max_images]):
        img = train_df.loc[idx].images
        mask = train_df.loc[idx].masks
        ax = axs[int(i / grid_width), i % grid_width]
        ax.imshow(img, cmap="Greys")
        ax.imshow(mask, alpha=0.3, cmap="Greens")
        ax.text(1, img_size_ori-1, train_df.loc[idx].z, color="black")
        ax.text(img_size_ori - 1, 1, round(train_df.loc[idx].coverage, 2), color="black", ha="right", va="top")
        ax.text(1, 1, train_df.loc[idx].coverage_class, color="black", ha="left", va="top")
        ax.set_yticklabels([])
        ax.set_xticklabels([])
    plt.suptitle("Green: salt. Top-left: coverage class, top-right: salt coverage, bottom-left: depth")
    
    
    # # Create train/validation split stratified by salt coverage
    # Using the salt coverage as a stratification criterion. Also show an image to check for correct upsampling.
    
    # In[ ]:
    
    
    ids_train, ids_valid, x_train, x_valid, y_train, y_valid, cov_train, cov_test, depth_train, depth_test = train_test_split(
        train_df.index.values,
        np.array(train_df.images.map(upsample).tolist()).reshape(-1, img_size_target, img_size_target, 1), 
        np.array(train_df.masks.map(upsample).tolist()).reshape(-1, img_size_target, img_size_target, 1), 
        train_df.coverage.values,
        train_df.z.values,
        test_size=0.2, stratify=train_df.coverage_class, random_state=1337)
    
    
    # In[ ]:
    
    
    tmp_img = np.zeros((img_size_target, img_size_target), dtype=train_df.images.loc[ids_train[10]].dtype)
    tmp_img[:img_size_ori, :img_size_ori] = train_df.images.loc[ids_train[10]]
    fix, axs = plt.subplots(1, 2, figsize=(15,5))
    axs[0].imshow(tmp_img, cmap="Greys")
    axs[0].set_title("Original image")
    axs[1].imshow(x_train[10].squeeze(), cmap="Greys")
    axs[1].set_title("Scaled image")
    
    
     # In[ ]:Build model 
     
    input_layer = Input((img_size_target, img_size_target, 1))
    output_layer = build_model(input_layer, 16)
    model = Model(input_layer, output_layer) 
    model.compile(loss="binary_crossentropy", optimizer="adam", metrics=["accuracy"])
    model.summary() 
    
    # In[ ]:Data augmentation
    
    x_train = np.append(x_train, [np.fliplr(x) for x in x_train], axis=0)
    y_train = np.append(y_train, [np.fliplr(x) for x in y_train], axis=0)
    fig, axs = plt.subplots(2, 10, figsize=(15,3))
    for i in range(10):
        axs[0][i].imshow(x_train[i].squeeze(), cmap="Greys")
        axs[0][i].imshow(y_train[i].squeeze(), cmap="Greens", alpha=0.3)
        axs[1][i].imshow(x_train[int(len(x_train)/2 + i)].squeeze(), cmap="Greys")
        axs[1][i].imshow(y_train[int(len(y_train)/2 + i)].squeeze(), cmap="Greens", alpha=0.3)
    fig.suptitle("Top row: original images, bottom row: augmented images")
    
    
    # In[ ]: Training
    
    early_stopping = EarlyStopping(patience=10, verbose=1)
    model_checkpoint = ModelCheckpoint("./keras.model", save_best_only=True, verbose=1)
    reduce_lr = ReduceLROnPlateau(factor=0.1, patience=5, min_lr=0.00001, verbose=1)
    
    epochs = 200
    batch_size = 32
    
    ################################history = model.fit(x_train, y_train,
                        ################################validation_data=[x_valid, y_valid], 
                        ################################epochs=epochs,
                        ################################batch_size=batch_size,
                        ################################callbacks=[early_stopping, model_checkpoint, reduce_lr])
    #################################fig, (ax_loss, ax_acc) = plt.subplots(1, 2, figsize=(15,5))
    #################################ax_loss.plot(history.epoch, history.history["loss"], label="Train loss")
    #################################ax_loss.plot(history.epoch, history.history["val_loss"], label="Validation loss")
    #################################ax_acc.plot(history.epoch, history.history["acc"], label="Train accuracy")
    #################################ax_acc.plot(history.epoch, history.history["val_acc"], label="Validation accuracy")
    model = load_model("./keras.model")

    
    # In[ ]:Predict the validation set to do a sanity check
    
      # Again plot some sample images including the predictions.
      
    preds_valid = model.predict(x_valid).reshape(-1, img_size_target, img_size_target)
    preds_valid = np.array([downsample(x) for x in preds_valid])
    y_valid = np.array([downsample(x) for x in y_valid])
    max_images = 60
    grid_width = 15
    grid_height = int(max_images / grid_width)
    fig, axs = plt.subplots(grid_height, grid_width, figsize=(grid_width, grid_height))
    for i, idx in enumerate(ids_train[:max_images]):
        img = train_df.loc[idx].images
        mask = train_df.loc[idx].masks
        pred = preds_valid[i]
        
        # ---------- 加入crf----------
        
        parser = get_parser()
        args = parser.parse_args()
        # Load data
        image = np.uint8(np.expand_dims(img, axis=0)*255)###############cichugenggai 
        image = image.transpose(1,2,0)
        label = np.uint8(pred)
        # Produce unary by adding noise to label
        unary = synthetic.augment_label(label, num_classes=21)
        # Compute CRF inference
        prediction = do_crf_inference(image, unary, args)
        # Plot output
     #   plot_results(image, unary, prediction, label, args)
        logging.info("Thank you for trying ConvCRFs.") 
        
        #-----------------------------
        
        ax = axs[int(i / grid_width), i % grid_width]
        ax.imshow(img, cmap="Greys")
        ax.imshow(mask, alpha=0.3, cmap="Greens")
        ax.imshow(pred, alpha=0.3, cmap="OrRd")
        ax.imshow(label, alpha=0.3, cmap="Blues")
        
        ax.text(1, img_size_ori-1, train_df.loc[idx].z, color="black")
        ax.text(img_size_ori - 1, 1, round(train_df.loc[idx].coverage, 2), color="black", ha="right", va="top")
        ax.text(1, 1, train_df.loc[idx].coverage_class, color="black", ha="left", va="top")
        ax.set_yticklabels([])
        ax.set_xticklabels([])
    plt.suptitle("Green: salt, Red: prediction. Top-left: coverage class, top-right: salt coverage, bottom-left: depth")
    plt.show()
    # In[ ]:Scoring
    
     #  Score the model and do a threshold optimization by the best IoU.
     
    thresholds = np.linspace(0, 1, 50)
    ious = np.array([iou_metric_batch(y_valid, np.int32(preds_valid > threshold)) for threshold in tqdm_notebook(thresholds)])
    threshold_best_index = np.argmax(ious[9:-10]) + 9
    iou_best = ious[threshold_best_index]
    threshold_best = thresholds[threshold_best_index]
    plt.plot(thresholds, ious)
    plt.plot(threshold_best, iou_best, "xr", label="Best threshold")
    plt.xlabel("Threshold")
    plt.ylabel("IoU")
    plt.title("Threshold vs IoU ({}, {})".format(threshold_best, iou_best))
    plt.legend()
     
    # In[ ]: Another sanity check with adjusted threshold
     
      # Again some sample images with the adjusted threshold.
      
    max_images = 60
    grid_width = 15
    grid_height = int(max_images / grid_width)
    fig, axs = plt.subplots(grid_height, grid_width, figsize=(grid_width, grid_height))
    for i, idx in enumerate(ids_train[:max_images]):
        img = train_df.loc[idx].images
        mask = train_df.loc[idx].masks
        pred = preds_valid[i]
        ax = axs[int(i / grid_width), i % grid_width]
        ax.imshow(img, cmap="Greys")
        ax.imshow(mask, alpha=0.3, cmap="Greens")
        ax.imshow(np.array(np.round(pred > threshold_best), dtype=np.float32), alpha=0.3, cmap="OrRd")
        ax.text(1, img_size_ori-1, train_df.loc[idx].z, color="black")
        ax.text(img_size_ori - 1, 1, round(train_df.loc[idx].coverage, 2), color="black", ha="right", va="top")
        ax.text(1, 1, train_df.loc[idx].coverage_class, color="black", ha="left", va="top")
        ax.set_yticklabels([])
        ax.set_xticklabels([])
    plt.suptitle("Green: salt, Red: prediction. Top-left: coverage class, top-right: salt coverage, bottom-left: depth")
    
    #In[ ]: Submission
    
       # Load, predict and submit the test image predictions.     

    x_test = np.array([upsample(np.array(load_img("../input/test/images/{}.png".format(idx), grayscale=True))) / 255 for idx in tqdm_notebook(test_df.index)]).reshape(-1, img_size_target, img_size_target, 1)
    preds_test = model.predict(x_test)
    pred_dict = {idx: RLenc(np.round(downsample(preds_test[i]) > threshold_best)) for i, idx in enumerate(tqdm_notebook(test_df.index.values))}
    sub = pd.DataFrame.from_dict(pred_dict,orient='index')
    sub.index.names = ['id']
    sub.columns = ['rle_mask']
    sub.to_csv('submission.csv')     
    
     