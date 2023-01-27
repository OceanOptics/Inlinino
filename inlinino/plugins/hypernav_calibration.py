from dataclasses import dataclass
from typing import Union

import numpy as np


N_PIXELS = 2048


@dataclass
class HyperNavDarkSpecStats:
    spectral_shape: Union[float, np.ndarray, bool] = float('nan')
    mean_value: Union[float, np.ndarray, bool] = float('nan')
    noise_level: Union[float, np.ndarray, bool] = float('nan')


def compute_dark_stats(data: np.ndarray) -> HyperNavDarkSpecStats:
    """
    Compute statistics on dark spectrum from HyperNav spectrophotometer

    :param data: <np.ndarray(N_OBSERVATIONS, N_PIXELS)> spectrum on which to compute statistics
    :return: HyperNavDarkSpecStats
    """
    return HyperNavDarkSpecStats(
        spectral_shape=np.mean(np.std(data[~np.any(np.isnan(data), axis=1), :], axis=1)),
        mean_value=np.nanmean(data),
        noise_level=np.nanmean(np.nanstd(data, axis=0)),
    )


def test_dark(stats: HyperNavDarkSpecStats) -> HyperNavDarkSpecStats:
    """
    Pass/Fail test for characterization of dark from HyperNav spectrometer + board assembly

    :param stats: <HyperNavDarkSpecStats> statistics on dark spectrum computed with from compute_dark_stats
    :return: HyperNavDarkSpecStats
    """
    return HyperNavDarkSpecStats(
        spectral_shape=stats.spectral_shape < 100,
        mean_value=stats.mean_value < 6000,
        noise_level=stats.noise_level < 200,
    )


@dataclass
class HyperNavLightSpecStats:
    pixel_registration: Union[float, np.ndarray, bool] = float('nan')
    peak_value: Union[float, np.ndarray, bool] = float('nan')


def compute_light_stats(data: np.ndarray) -> HyperNavLightSpecStats:
    """
    Compute statistics on light spectrum from HyperNav spectrophotometer

    :param data: <np.ndarray(N_OBSERVATIONS, N_PIXELS)> spectrum on which to compute statistics
    :return: HyperNavLightSpecStats
    """
    return HyperNavLightSpecStats(
        pixel_registration=np.nan,  # TODO Implement test
        peak_value=np.nanpercentile(data, 98),
    )


def test_light(stats: HyperNavLightSpecStats) -> HyperNavLightSpecStats:
    """
    Pass/Fail test for characterization of light from HyperNav spectrometer + board assembly

    :param stats: <HyperNavLightSpecStats> statistics on light spectrum computed with from compute_light_stats
    :return: HyperNavLightSpecStats
    """
    return HyperNavLightSpecStats(
        pixel_registration=False,  # TODO Implement test
        peak_value=stats.peak_value > 30000,
    )
