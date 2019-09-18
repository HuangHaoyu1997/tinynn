"""Network layers and activation layers."""

import numpy as np

from core.initializer import XavierUniformInit
from core.initializer import ZerosInit


class Layer(object):

    def __init__(self, name):
        self.name = name

        self.params, self.grads = {}, {}
        self.is_training = True

    def forward(self, inputs):
        raise NotImplementedError

    def backward(self, grad):
        raise NotImplementedError

    def set_phase(self, phase):
        self.is_training = True if phase == "TRAIN" else False


class Dense(Layer):

    def __init__(self,
                 num_out,
                 num_in=None,
                 w_init=XavierUniformInit(),
                 b_init=ZerosInit()):
        super().__init__("Linear")
        self.initializers = {"w": w_init, "b": b_init}
        self.shapes = {"w": [num_in, num_out], "b": [1, num_out]}
        self.params = {"w": None, "b": None}

        self.is_init = False
        if num_in is not None:
            self._init_parameters(num_in)

        self.inputs = None

    def forward(self, inputs):
        # lazy initialize
        if not self.is_init:
            self._init_parameters(inputs.shape[1])

        self.inputs = inputs
        return inputs @ self.params["w"] + self.params["b"]

    def backward(self, grad):
        self.grads["w"] = self.inputs.T @ grad
        self.grads["b"] = np.sum(grad, axis=0)
        return grad @ self.params["w"].T

    def _init_parameters(self, input_size):
        self.shapes["w"][0] = input_size
        self.params["w"] = self.initializers["w"](shape=self.shapes["w"])
        self.params["b"] = self.initializers["b"](shape=self.shapes["b"])
        self.is_init = True


class Conv2D(Layer):

    def __init__(self,
                 kernel,
                 stride=(1, 1),
                 padding="SAME",
                 w_init=XavierUniformInit(),
                 b_init=ZerosInit()):
        """
        Implement 2D convolution layer
        :param kernel: A list/tuple of int that has length 4 (height, width, in_channels, out_channels)
        :param stride: A list/tuple of int that has length 2 (height, width)
        :param padding: String ["SAME", "VALID"]
        :param w_init: weight initializer
        :param b_init: bias initializer
        """
        super().__init__("Conv2D")

        # verify arguments
        assert len(kernel) == 4
        assert len(stride) == 2
        assert padding in ("FULL", "SAME", "VALID")

        self.padding_mode = padding
        self.kernel = kernel
        self.stride = stride
        self.initializers = {"w": w_init, "b": b_init}

        self.is_init = False

        self.inputs = None
        self.cache = None  # cache

    def forward(self, inputs):
        # lazy initialization
        if not self.is_init:
            self._init_parameters()

        k_h, k_w = self.kernel[:2]
        s_h, s_w = self.stride

        pad = self._get_padding([k_h, k_w], self.padding_mode)

        # pad the inputs with the edge values
        pad_width = ((0, 0), (pad[0], pad[1]), (pad[2], pad[3]), (0, 0))
        padded = np.pad(inputs, pad_width=pad_width, mode="edge")

        in_n, in_h, in_w, in_c = inputs.shape
        padded_h, padded_w = padded.shape[1:3]

        # resulting feature maps' sizes
        out_h = int((padded_h - k_h) / s_h + 1)
        out_w = int((padded_w - k_w) / s_w + 1)
        out_c = self.kernel[-1]

        kernel = self.params["w"]
        ker_len = np.prod(kernel.shape[:3])  # flatten kernel length
        patches = list()

        # expand inputs matrix before convolution by matrix product.
        # An example:
        # input = | 43  16  78 |      kernel = | 4  6 |
        #         | 34  76  95 |               | 7  9 |
        #         | 35   8  46 |
        #
        # After expansion and flattening:
        # input = | 43 16 34 76 |     kernel = | 4 |
        #         | 16 78 76 95 |              | 6 |
        #  (X)    | 34 76 35  8 |      (W)     | 7 |
        #         | 76 95  8 46 |              | 9 |
        for i, row in enumerate(range(0, padded_h - k_h + 1, s_h)):
            row_patches = list()
            for j, col in enumerate(range(0, padded_w - k_w + 1, s_w)):
                patch = padded[:, row:row+k_h, col:col+k_w, :]
                # lay out local patch
                row_patches.append(patch.reshape(-1, ker_len))
            patches.append(row_patches)
        # organize local patches to a (out_h, out_w, batch, ker_len) matrix
        patches = np.asarray(patches)

        X_matrix = patches.transpose([2, 0, 1, 3])
        X_matrix = X_matrix.reshape((-1, ker_len))  # (batch * out_h * out_w, ker_len)

        # transformed kernel (ker_len, out_c)
        W_matrix = kernel.reshape((ker_len, -1))
        outputs = (X_matrix @ W_matrix).reshape((in_n, out_h, out_w, out_c))

        self.cache = {"in_n": in_n, "in_img_size": (in_h, in_w, in_c),
                      "kernel_size": (k_h, k_w, in_c), "stride": (s_h, s_w),
                      "pad": pad, "pad_img_size": (padded_h, padded_w, in_c),
                      "out_img_size": (out_h, out_w, out_c),
                      "X_matrix": X_matrix, "W_matrix": W_matrix}

        outputs += self.params["b"]
        return outputs

    def backward(self, grad):
        # read save values form cache
        in_n = self.cache["in_n"]  # batch size
        in_h, in_w, in_c = self.cache["in_img_size"]
        k_h, k_w, _ = self.cache["kernel_size"]
        s_h, s_w = self.cache["stride"]
        out_h, out_w, out_c = self.cache["out_img_size"]
        padded_h, padded_w, _ = self.cache["pad_img_size"]
        pad = self.cache["pad"]

        # gradient of parameters
        d_w = self.cache["X_matrix"].T @ grad.reshape((-1, out_c))
        self.grads["w"] = d_w.reshape(self.params["w"].shape)
        self.grads["b"] = np.sum(grad, axis=(0, 1, 2))

        # gradients to lower layers
        d_X_matrix = grad @ self.cache["W_matrix"].T
        # transform gradients back to original shape as d_in
        d_in = np.zeros(shape=(in_n, padded_h, padded_w, in_c))
        for i, col in enumerate(range(0, padded_h - k_h + 1, s_h)):
            for j, row in enumerate(range(0, padded_w - k_w + 1, s_w)):
                patch = d_X_matrix[:, i, j, :].reshape(
                    (in_n, k_h, k_w, in_c))
                d_in[:, col:col+k_h, row:row+k_w, :] += patch
        # cut off padding
        d_in = d_in[:, pad[0]:padded_h-pad[1], pad[2]:padded_w-pad[3], :]
        return d_in

    @staticmethod
    def _get_padding(ks, mode):
        """
        :param ks (kernel size) [p, q]
        :param mode (FULL|VALID|SAME)
            - FULL: to generate maximum sized feature map, allow only one valid
            pixel to be mapped at the corners.
            - VALID: to generate minimal sized feature map, require all kernel
            units mapping to valid input area.
            - SAME: require generated feature map to have the same (or almost
            the same) size as input area.
        :return: list of padding (top, bottom, left, right) in different modes
        """
        pad = None
        if mode == "FULL":
            pad = [ks[0] - 1, ks[1] - 1, ks[0] - 1, ks[1] - 1]
        elif mode == "VALID":
            pad = [0, 0, 0, 0]
        elif mode == "SAME":
            pad = [(ks[0] - 1) // 2, (ks[0] - 1) // 2,
                   (ks[1] - 1) // 2, (ks[1] - 1) // 2]
            if ks[0] % 2 == 0:
                pad[1] += 1
            if ks[1] % 2 == 0:
                pad[3] += 1
        else:
            print("Invalid mode")
        return pad

    def _init_parameters(self):
        self.params["w"] = self.initializers["w"](self.kernel)
        self.params["b"] = self.initializers["b"](self.kernel[-1])
        self.is_init = True


class MaxPool2D(Layer):

    def __init__(self,
                 pool_size,
                 stride,
                 padding="VALID"):
        """
        Implement 2D max-pooling layer
        :param pool_size: A list/tuple of 2 integers (pool_height, pool_width)
        :param stride: A list/tuple of 2 integers (stride_height, stride_width)
        :param padding: A string ("SAME", "VALID")
        """
        super().__init__("MaxPooling2D")
        # validate arguments
        assert len(pool_size) == 2
        assert len(stride) == 2
        assert padding in ("VALID", "SAME")

        self.pool_size = pool_size
        self.stride = stride
        self.padding_mode = padding

        self.cache = None

    def forward(self, inputs):
        in_n, in_h, in_w, in_c = inputs.shape
        pad = self._get_padding([in_h, in_w], self.pool_size, self.stride,
                                self.padding_mode)
        pad_width = ((0, 0), (pad[0], pad[1]), (pad[2], pad[3]), (0, 0))
        padded = np.pad(inputs, pad_width=pad_width, mode="constant")
        pad_h, pad_w = padded.shape[1:3]
        (s_h, s_w), (pool_h, pool_w) = self.stride, self.pool_size
        out_h, out_w = pad_h // s_h, pad_w // s_w
        patches_list, max_pos_list = list(), list()
        for col in range(0, pad_h, s_h):
            for row in range(0, pad_w, s_w):
                pool = padded[:, col:col + pool_h, row:row + pool_w, :]
                pool = pool.reshape((in_n, -1, in_c))
                max_pos_list.append(np.argmax(pool, axis=1))
                patches_list.append(np.max(pool, axis=1))
        outputs = np.array(patches_list).transpose((1, 0, 2)).reshape(
            (in_n, out_h, out_w, in_c))
        max_pos = np.array(max_pos_list).transpose((1, 0, 2)).reshape(
            (in_n, out_h, out_w, in_c))

        self.cache = {"in_n": in_n, "in_img_size": (in_h, in_w, in_c),
                      "stride": (s_h, s_w), "pad": (pad_h, pad_w),
                      "pool": (pool_h, pool_w), "max_pos": max_pos,
                      "out_img_size": (out_h, out_w, in_c)}
        return outputs

    def backward(self, grad):
        in_n, (in_h, in_w, in_c) = self.cache["in_n"], self.cache["in_img_size"]
        s_h, s_w = self.cache["stride"]
        pad_h, pad_w = self.cache["pad"]
        pool_h, pool_w = self.cache["pool"]

        d_in = np.zeros(shape=(in_n, pad_h, pad_w, in_c))
        for i, col in enumerate(range(0, pad_h, s_h)):
            for j, row in enumerate(range(0, pad_w, s_w)):
                _max_pos = self.cache["max_pos"][:, i, j, :]
                _grad = grad[:, i, j, :]
                mask = np.eye(pool_h * pool_w)[_max_pos].transpose((0, 2, 1))
                region = np.repeat(_grad[:, np.newaxis, :],
                                   pool_h * pool_w, axis=1) * mask
                region = region.reshape((in_n, pool_h, pool_w, in_c))
                d_in[:, col:col + pool_h, row:row + pool_w, :] = region
        return d_in

    def _get_padding(self, input_size, pool_size, stride, mode):
        h_pad = self._get_padding_1d(
            input_size[0], pool_size[0], stride[0], mode)
        w_pad = self._get_padding_1d(
            input_size[1], pool_size[1], stride[1], mode)
        return h_pad + w_pad

    @staticmethod
    def _get_padding_1d(input_size, pool_size, stride, mode):
        if mode == "SAME":
            r = input_size % stride
            if r == 0:
                n_pad = max(pool_size - stride, 0)
            else:
                n_pad = max(pool_size, stride) - r
        else:
            n_pad = 0
        half = n_pad // 2
        pad = [half, half] if n_pad % 2 == 0 else [half, half + 1]
        return pad


class Flatten(Layer):

    def __init__(self):
        super().__init__("Flatten")
        self.input_shape = None

    def forward(self, inputs):
        self.input_shape = inputs.shape
        return inputs.ravel().reshape(inputs.shape[0], -1)

    def backward(self, grad):
        return grad.reshape(self.input_shape)


class Dropout(Layer):

    def __init__(self, keep_prob=0.5):
        super().__init__("Dropout")
        self._keep_prob = keep_prob
        self._multiplier = None

    def forward(self, inputs):
        if self.is_training:
            multiplier = np.random.binomial(
                1, self._keep_prob, size=inputs.shape)
            self._multiplier = multiplier / self._keep_prob
            outputs = inputs * self._multiplier
        else:
            outputs = inputs
        return outputs

    def backward(self, grad):
        assert self.is_training is True
        return grad * self._multiplier


class Activation(Layer):

    def __init__(self, name):
        super().__init__(name)
        self.inputs = None

    def forward(self, inputs):
        self.inputs = inputs
        return self.func(inputs)

    def backward(self, grad):
        return self.derivative_func(self.inputs) * grad

    def func(self, x):
        raise NotImplementedError

    def derivative_func(self, x):
        raise NotImplementedError


class Sigmoid(Activation):

    def __init__(self):
        super().__init__("Sigmoid")

    def func(self, x):
        return 1.0 / (1.0 + np.exp(-x))

    def derivative_func(self, x):
        return self.func(x) * (1.0 - self.func(x))


class Softplus(Activation):

    def __init__(self):
        super().__init__("Softplus")

    def func(self, x):
        return np.log(1.0 + np.exp(-np.abs(x))) + np.maximum(x, 0.0)

    def derivative_func(self, x):
        return 1.0 / (1.0 + np.exp(-x))


class Tanh(Activation):

    def __init__(self):
        super().__init__("Tanh")

    def func(self, x):
        return np.tanh(x)

    def derivative_func(self, x):
        return 1.0 - self.func(x) ** 2


class ReLU(Activation):

    def __init__(self):
        super().__init__("ReLU")

    def func(self, x):
        return np.maximum(x, 0.0)

    def derivative_func(self, x):
        return x > 0.0


class LeakyReLU(Activation):

    def __init__(self, slope=0.2):
        super().__init__("LeakyReLU")
        self._slope = slope

    def func(self, x):
        x = x.copy()
        x[x < 0.0] *= self._slope
        return x

    def derivative_func(self, x):
        dx = np.ones_like(x)
        dx[x < 0.0] = self._slope
        return dx
