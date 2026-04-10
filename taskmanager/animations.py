"""Shared animation helpers using QPropertyAnimation."""

from PySide6.QtCore import (
    QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup,
    QSequentialAnimationGroup, QAbstractAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect

from . import constants


def animate_archive(widget, target_pos, on_finished=None):
    """Shrink + fly the widget toward target_pos, then call on_finished."""
    # Unlock fixed-size constraints so the shrink animation can work
    widget.setMinimumSize(0, 0)
    widget.setMaximumSize(16777215, 16777215)

    group = QParallelAnimationGroup(widget)

    # Move toward archive
    move = QPropertyAnimation(widget, b"pos", widget)
    move.setDuration(constants.ARCHIVE_ANIM_DURATION)
    move.setStartValue(widget.pos())
    move.setEndValue(target_pos)
    move.setEasingCurve(QEasingCurve.InBack)
    group.addAnimation(move)

    # Fade out
    opacity_effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(opacity_effect)
    fade = QPropertyAnimation(opacity_effect, b"opacity", widget)
    fade.setDuration(constants.ARCHIVE_ANIM_DURATION)
    fade.setStartValue(1.0)
    fade.setEndValue(0.0)
    fade.setEasingCurve(QEasingCurve.InQuad)
    group.addAnimation(fade)

    # Size shrink
    shrink = QPropertyAnimation(widget, b"size", widget)
    shrink.setDuration(constants.ARCHIVE_ANIM_DURATION)
    shrink.setStartValue(widget.size())
    shrink.setEndValue(widget.size() / 3)
    shrink.setEasingCurve(QEasingCurve.InBack)
    group.addAnimation(shrink)

    if on_finished:
        group.finished.connect(on_finished)

    group.start(QAbstractAnimation.DeleteWhenStopped)
    return group


def animate_slide(widget, target_pos, on_finished=None):
    """Smoothly slide a widget to target_pos."""
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(constants.SLIDE_ANIM_DURATION)
    anim.setStartValue(widget.pos())
    anim.setEndValue(target_pos)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    if on_finished:
        anim.finished.connect(on_finished)

    anim.start(QAbstractAnimation.DeleteWhenStopped)
    return anim


def animate_appear(widget):
    """Fade-in a widget when it first appears."""
    opacity_effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(opacity_effect)
    opacity_effect.setOpacity(0.0)

    fade = QPropertyAnimation(opacity_effect, b"opacity", widget)
    fade.setDuration(constants.APPEAR_ANIM_DURATION)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.OutCubic)
    fade.start(QAbstractAnimation.DeleteWhenStopped)
    return fade
