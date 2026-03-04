#!/usr/bin/env python3
"""
Real-Time Auto Labeler Engine
==============================

Streaming version of the auto-labeling algorithm.
Maintains a rolling window of recent data and continuously
determines who the active speaker is.

Used by live_collection_graph.py during data collection.
"""

import numpy as np
from collections import deque
from datetime import timedelta


class RealtimeLabeler:
    """
    Streaming speaker-detection engine.

    Feed it data points via `add_sample()` and query
    `get_active_speaker()` at any time.
    """

    def __init__(self):
        # ---- Tunable parameters (matched to auto_label.py) ----
        self.window_sec = 60          # rolling baseline window
        self.short_window_sec = 1     # fast response window
        self.time_bin_ms = 500        # bin resolution
        self.speech_threshold_quantile = 0.45
        self.min_speech_score = 0.3
        self.high_score_fallback = 2.0
        self.vote_window_bins = 5
        self.min_vote_ratio = 0.35

        self.accel_weight = 1.2
        self.accel_clip = 2.5

        # ---- Internal state ----
        # Per-badge rolling buffers: badge_name -> deque of dicts
        #   each dict: {timestamp, sound, acceleration}
        self.badge_buffers = {}
        self.max_buffer_size = 3000   # ~5 min at 10 Hz

        # Recent bin winners for majority vote
        self.recent_bin_winners = deque(maxlen=50)  # last ~25 seconds of bins
        self.last_bin_time = None

        # Current result
        self._active_speaker = None
        self._speaker_scores = {}     # badge -> latest speech_score
        self._badge_labels = {}       # badge -> "active" / "not_active"

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------
    def add_sample(self, timestamp, badge_name, sound, acceleration):
        """
        Feed a single data point into the labeler.

        Parameters
        ----------
        timestamp : datetime
        badge_name : str
        sound : float
        acceleration : float
        """
        if badge_name not in self.badge_buffers:
            self.badge_buffers[badge_name] = deque(maxlen=self.max_buffer_size)

        self.badge_buffers[badge_name].append({
            'timestamp': timestamp,
            'sound': sound,
            'acceleration': acceleration,
        })

        # Re-evaluate on every new bin boundary
        if self.last_bin_time is None:
            self.last_bin_time = self._floor_bin(timestamp)

        current_bin = self._floor_bin(timestamp)
        if current_bin > self.last_bin_time:
            self._evaluate_bin(current_bin)
            self.last_bin_time = current_bin

    def get_active_speaker(self):
        """Return the badge name of the current active speaker, or None."""
        return self._active_speaker

    def get_all_labels(self):
        """Return dict: badge_name -> 'active' / 'not_active'."""
        result = {}
        for badge in self.badge_buffers:
            result[badge] = self._badge_labels.get(badge, "not_active")
        return result

    def get_speaker_scores(self):
        """Return dict: badge_name -> latest speech_score (for display)."""
        return dict(self._speaker_scores)

    def get_known_badges(self):
        """Return list of all badge names seen so far."""
        return list(self.badge_buffers.keys())

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------
    def _floor_bin(self, ts):
        """Floor a timestamp to the nearest time_bin_ms."""
        ms = int(ts.timestamp() * 1000)
        floored = (ms // self.time_bin_ms) * self.time_bin_ms
        from datetime import datetime
        return datetime.fromtimestamp(floored / 1000.0)

    def _iqr_stats(self, values):
        """Compute (floor, spread) from a list of values using IQR."""
        if len(values) < 5:
            return np.median(values), max(1.0, np.std(values))
        q25 = np.percentile(values, 25)
        q75 = np.percentile(values, 75)
        spread = max(1.0, q75 - q25)
        return q25, spread

    def _compute_speech_score(self, badge_name, current_bin):
        """Compute the speech score for a badge at a given bin time."""
        buf = self.badge_buffers.get(badge_name)
        if not buf or len(buf) < 3:
            return 0.0, False

        # Gather samples in the window
        cutoff_long = current_bin - timedelta(seconds=self.window_sec)
        cutoff_short = current_bin - timedelta(seconds=self.short_window_sec)

        long_sounds = []
        long_accels = []
        short_sounds = []
        recent_sounds = []

        for sample in buf:
            ts = sample['timestamp']
            if ts >= cutoff_long:
                long_sounds.append(sample['sound'])
                long_accels.append(sample['acceleration'])
            if ts >= cutoff_short:
                short_sounds.append(sample['sound'])
            # All recent samples for quantile threshold
            recent_sounds.append(sample['sound'])

        if not long_sounds or not short_sounds:
            return 0.0, False

        # IQR normalization for sound
        sound_floor, sound_spread = self._iqr_stats(long_sounds)
        current_sound = np.mean(short_sounds)
        norm_sound = (current_sound - sound_floor) / sound_spread

        # Speech presence check
        sound_threshold = np.quantile(recent_sounds[-min(len(recent_sounds), 600):],
                                       self.speech_threshold_quantile)
        speech_present = current_sound > sound_threshold

        # Acceleration normalization
        speech_score = norm_sound
        if long_accels and self.accel_weight > 0:
            accel_floor, accel_spread = self._iqr_stats(long_accels)
            # Use recent acceleration
            recent_accels = [s['acceleration'] for s in buf
                             if s['timestamp'] >= cutoff_short]
            if recent_accels:
                current_accel = np.mean(recent_accels)
                norm_accel = (current_accel - accel_floor) / accel_spread
                norm_accel = max(0, min(norm_accel, self.accel_clip))
                speech_score += self.accel_weight * norm_accel

        return speech_score, speech_present

    def _evaluate_bin(self, current_bin):
        """Determine the active speaker for the current time bin."""
        # Compute scores for all badges
        candidates = {}
        for badge_name in self.badge_buffers:
            score, speech_present = self._compute_speech_score(badge_name, current_bin)
            self._speaker_scores[badge_name] = score

            if (speech_present or score >= self.high_score_fallback) and score >= self.min_speech_score:
                candidates[badge_name] = score

        # Raw winner for this bin
        raw_winner = None
        if candidates:
            raw_winner = max(candidates, key=candidates.get)

        self.recent_bin_winners.append(raw_winner)

        # Majority vote over recent bins
        vote_window = list(self.recent_bin_winners)[-self.vote_window_bins:]
        votes = {}
        for w in vote_window:
            if w is not None:
                votes[w] = votes.get(w, 0) + 1

        min_votes = max(1, round(self.vote_window_bins * self.min_vote_ratio))

        # Reset all labels
        for badge in self.badge_buffers:
            self._badge_labels[badge] = "not_active"

        self._active_speaker = None

        if votes:
            top_badge, top_votes = max(votes.items(), key=lambda kv: kv[1])
            if top_votes >= min_votes:
                self._active_speaker = top_badge
                self._badge_labels[top_badge] = "active"
