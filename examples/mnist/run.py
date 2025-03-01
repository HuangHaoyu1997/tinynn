"""Example code for MNIST classification."""

import argparse
import os
import time

import numpy as np
import tinynn as tn


def main():
    if args.seed >= 0:
        tn.seeder.random_seed(args.seed)

    mnist = tn.dataset.MNIST(args.data_dir, one_hot=True)
    train_x, train_y = mnist.train_set
    test_x, test_y = mnist.test_set

    if args.model_type == "mlp":
        # A multilayer perceptron model
        net = tn.net.Net([
            tn.layer.Dense(16),
            tn.layer.ReLU(),
            tn.layer.Dense(10)
        ])
    elif args.model_type == "cnn":
        # A LeNet-5 model with activation function changed to ReLU
        train_x = train_x.reshape((-1, 28, 28, 1))
        test_x = test_x.reshape((-1, 28, 28, 1))
        net = tn.net.Net([
            tn.layer.Conv2D(kernel=[5, 5, 1, 6], stride=[1, 1]),
            tn.layer.ReLU(),
            tn.layer.MaxPool2D(pool_size=[2, 2], stride=[2, 2]),
            tn.layer.Conv2D(kernel=[5, 5, 6, 16], stride=[1, 1]),
            tn.layer.ReLU(),
            tn.layer.MaxPool2D(pool_size=[2, 2], stride=[2, 2]),
            tn.layer.Flatten(),
            tn.layer.Dense(120),
            tn.layer.ReLU(),
            tn.layer.Dense(84),
            tn.layer.ReLU(),
            tn.layer.Dense(10)
        ])
    elif args.model_type == "rnn":
        # A simple recurrent neural net to classify images.
        train_x = train_x.reshape((-1, 28, 28))
        test_x = test_x.reshape((-1, 28, 28))
        net = tn.net.Net([
            tn.layer.RNN(num_hidden=30),
            tn.layer.Dense(10)
        ])
    elif args.model_type == "lstm":
        train_x = train_x.reshape((-1, 28, 28))
        test_x = test_x.reshape((-1, 28, 28))
        net = tn.net.Net([
            tn.layer.LSTM(num_hidden=30),
            tn.layer.Dense(10)
        ])
    else:
        raise ValueError("Invalid argument: model_type")

    loss = tn.loss.SoftmaxCrossEntropy()
    optimizer = tn.optimizer.Adam(lr=args.lr)
    model = tn.model.Model(net=net, loss=loss, optimizer=optimizer)

    if args.model_path is not None:
        model.load(args.model_path)
        evaluate(model, test_x, test_y)
    else:
        iterator = tn.data_iterator.BatchIterator(batch_size=args.batch_size)
        for epoch in range(args.num_ep):
            t_start = time.time()
            for batch in iterator(train_x, train_y):
                pred = model.forward(batch.inputs)
                loss, grads = model.backward(pred, batch.targets)
                model.apply_grads(grads)
            print(f"Epoch {epoch} time cost: {time.time() - t_start}")
            # evaluate every epoch
            evaluate(model, test_x, test_y)

        # save model
        if not os.path.isdir(args.model_dir):
            os.makedirs(args.model_dir)
        model_name = f"mnist-{args.model_type}-epoch{args.num_ep}.pkl"
        model_path = os.path.join(args.model_dir, model_name)
        model.save(model_path)
        print(f"Model saved in {model_path}")


def evaluate(model, test_x, test_y):
    model.is_training = False
    test_pred = model.forward(test_x)
    test_pred_idx = np.argmax(test_pred, axis=1)
    test_y_idx = np.argmax(test_y, axis=1)
    accuracy, info = tn.metric.accuracy(test_pred_idx, test_y_idx)
    model.is_training = True
    print(f"accuracy: {accuracy:.4f} info: {info}")


if __name__ == "__main__":
    curr_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str,
                        default=os.path.join(curr_dir, "data"))
    parser.add_argument("--model_dir", type=str,
                        default=os.path.join(curr_dir, "models"))
    parser.add_argument("--model_path", type=str, default=None)
    parser.add_argument("--model_type", default="cnn", type=str,
                        help="[*mlp|cnn|rnn|lstm]")
    parser.add_argument("--num_ep", default=10, type=int)
    parser.add_argument("--lr", default=1e-3, type=float)
    parser.add_argument("--batch_size", default=128, type=int)
    parser.add_argument("--seed", default=-1, type=int)
    args = parser.parse_args()
    main()
