import numpy as np
import ctypes
from numpy.ctypeslib import ndpointer
import os
from matplotlib.offsetbox import AnchoredText
import matplotlib.pyplot as plt
import pickle
import gzip


lib = np.ctypeslib.load_library("histogram_c", os.path.dirname(__file__))
histogram = lib.histogram

histogram.argtypes = [ndpointer(ctypes.c_float, flags="C_CONTIGUOUS"),
                      ndpointer(ctypes.c_uint, flags="C_CONTIGUOUS"),
                      ndpointer(ctypes.c_uint, flags="C_CONTIGUOUS"),
                      ndpointer(ctypes.c_uint, flags="C_CONTIGUOUS"),
                      ndpointer(ctypes.c_float, flags="C_CONTIGUOUS"),
                      ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]

__all__ = ['Histogram1D']


class Histogram1D:

    def __init__(self, bin_edges, data_shape=()):

        self.data = np.zeros(data_shape + (bin_edges.shape[0] - 1, ),
                             dtype=np.uint32)
        self.shape = self.data.shape
        self.bins = np.sort(bin_edges).astype(np.float32)
        self.bin_centers = np.diff(self.bins) / 2. + self.bins[:-1]
        self.n_bins = self.bins.shape[0] - 1
        self.underflow = np.zeros(data_shape, dtype=np.uint32)
        self.overflow = np.zeros(data_shape, dtype=np.uint32)

    def __getitem__(self, item):

        if isinstance(item, int):

            item = (item, )

        data_shape = self.shape[len(item):-1]
        histogram = Histogram1D(bin_edges=self.bins, data_shape=data_shape)
        histogram.data = self.data[item]
        histogram.underflow = self.underflow[item]
        histogram.overflow = self.overflow[item]

        return histogram

    def fill(self, data_points, indices=()):
        """
        :param data_points: ndarray, nan values are ignored
        :param indices: indices of the histogram to be filled
        :return:
        """
        data = self.data[indices]
        underflow = self.underflow[indices]
        overflow = self.overflow[indices]

        shape = self.shape[len(indices):]
        bins = self.bins

        if data_points.shape[:-1] != shape[:-1]:
            raise IndexError('Invalid value for indices : {}, '
                             'data_points shape : {}'.format(indices,
                                                             data_points.shape
                                                             ))

        new_first_axis = 1
        for i in shape[:-1]:
            new_first_axis *= i

        data_points = data_points.reshape(new_first_axis, -1).astype(
            np.float32, order='C')

        n_pixels = data_points.shape[0]
        n_samples = data_points.shape[1]
        n_bins = self.n_bins + 1

        data = data.reshape(new_first_axis, -1)
        underflow = underflow.reshape(new_first_axis, -1)
        overflow = overflow.reshape(new_first_axis, -1)

        histogram(data_points, data, underflow, overflow,
                  bins, n_pixels, n_samples, n_bins)

        data = data.reshape(shape)
        underflow = underflow.reshape(shape[:-1])
        overflow = overflow.reshape(shape[:-1])

        self.data[indices] = data
        self.underflow[indices] = underflow
        self.overflow[indices] = overflow

    def reset(self):

        self.data.fill(0)
        self.underflow.fill(0)
        self.overflow.fill(0)

    def errors(self, index=[...]):

        return np.sqrt(self.data[index])

    def mean(self, index=[...], method='left'):

        if method == 'left':

            bins = self.bins[:-1]

        elif method == 'right':

            bins = self.bins[1:]

        elif method == 'mid':

            bins = self.bin_centers

        else:

            raise ValueError('Unknown method {}'.format(method))

        mean = np.sum(self.data[index] * bins, axis=-1)
        mean = mean / np.sum(self.data[index], axis=-1)

        return mean

    def std(self, index=[...], method='left'):

        if method == 'left':

            bins = self.bins[:-1]

        elif method == 'right':

            bins = self.bins[1:]

        elif method == 'mid':

            bins = self.bin_centers

        else:

            raise ValueError('Unknown method {}'.format(method))

        std = np.sum(self.data[index] * bins**2, axis=-1)
        std /= np.sum(self.data[index], axis=-1)
        std -= self.mean(index=index, method=method)**2
        return np.sqrt(std)

    def mode(self, index=[...]):

        if self.is_empty():

            return np.zeros(self.shape) * np.nan

        mode = self.bins[np.argmax(self.data[index], axis=-1)]
        return mode

    def min(self, index=[...]):

        if self.is_empty():

            return np.ones(self.shape) * np.nan

        else:

            data = self.data
            data[data == 0] = np.inf
            min = np.argmin(data, axis=-1)
            min = self.bin_centers[min]

            return min[index]

    def max(self, index=[...]):

        if self.is_empty():

            return np.ones(self.shape) * np.nan

        else:

            max = np.argmax(self.data, axis=-1)
            max = self.bin_centers[max]

        return max[index]

    def is_empty(self):

        n_points = np.sum(self.data)

        if n_points > 0:

            return False

        else:

            return True

    def _write_info(self, index):

        print('hello')
        print(self.min(index))
        print(self.max(index))

        text = ' counts : {}\n' \
               ' underflow : {}\n' \
               ' overflow : {}\n' \
               ' mean : {:.4f}\n' \
               ' std : {:.4f}\n' \
               ' mode : {:.1f}\n' \
               ' max : {:.2f}\n' \
               ' min : {:.2f}\n'.format(np.sum(self.data[index]),
                         np.sum(self.underflow[index]),
                         np.sum(self.overflow[index]),
                         self.mean(index=index),
                         self.std(index=index),
                         self.mode(index=index),
                         self.max(index=index),
                         self.min(index=index),
                         )

        print(text)

        return text

    def draw(self, index=(), axis=None, normed=False, log=False, legend=True,
             x_label='', label='Histogram', **kwargs):

        if axis is None:

            fig = plt.figure()
            axis = fig.add_subplot(111)

        x = self.bin_centers
        y = self.data[index]
        err = self.errors(index=index)
        mask = y > 0

        x = x[mask]
        y = y[mask]
        err = err[mask]

        if normed:

            weights = np.sum(y, axis=-1)
            y = y / weights
            err = err / weights

        steps = axis.step(x, y, where='mid',
                          label=label, **kwargs)
        axis.errorbar(x, y, yerr=err, linestyle='None',
                      color=steps[0].get_color())

        if legend:
            text = self._write_info(index)
            anchored_text = AnchoredText(text, loc=2)
            axis.add_artist(anchored_text)

        axis.set_xlabel(x_label)
        axis.set_ylabel('count' if not normed else 'probability')
        axis.legend(loc='best')

        if log:

            axis.set_yscale('log')

        return axis

    def save(self, path, **kwargs):

        with gzip.open(path, 'wb', **kwargs) as handle:

            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path):

        with gzip.open(path, 'rb') as handle:

            obj = pickle.load(handle)

        return obj
