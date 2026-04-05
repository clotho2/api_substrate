import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  withDelay,
  Easing,
} from 'react-native-reanimated';

interface AudioWaveformIconProps {
  active?: boolean;
  color?: string;
  size?: number;
}

const BAR_COUNT = 4;
const BASE_HEIGHT_RATIO = 0.3;
const MAX_HEIGHT_RATIO = 1.0;

export default function AudioWaveformIcon({
  active = false,
  color = '#FFFFFF',
  size = 20,
}: AudioWaveformIconProps) {
  const barWidth = Math.max(2, size / (BAR_COUNT * 2));
  const gap = Math.max(1, barWidth * 0.6);

  const animations = Array.from({ length: BAR_COUNT }, () => useSharedValue(BASE_HEIGHT_RATIO));

  useEffect(() => {
    if (active) {
      const durations = [400, 550, 350, 480];
      const peaks = [0.9, 1.0, 0.75, 0.85];
      const delays = [0, 100, 50, 150];

      animations.forEach((anim, i) => {
        anim.value = withDelay(
          delays[i],
          withRepeat(
            withSequence(
              withTiming(peaks[i] * MAX_HEIGHT_RATIO, {
                duration: durations[i],
                easing: Easing.inOut(Easing.sin),
              }),
              withTiming(BASE_HEIGHT_RATIO, {
                duration: durations[i],
                easing: Easing.inOut(Easing.sin),
              })
            ),
            -1,
            true
          )
        );
      });
    } else {
      animations.forEach((anim) => {
        anim.value = withTiming(BASE_HEIGHT_RATIO, { duration: 200 });
      });
    }
  }, [active]);

  const barStyles = animations.map((anim) =>
    useAnimatedStyle(() => ({
      height: anim.value * size,
    }))
  );

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      {barStyles.map((style, i) => (
        <Animated.View
          key={i}
          style={[
            {
              width: barWidth,
              borderRadius: barWidth / 2,
              backgroundColor: color,
              marginHorizontal: gap / 2,
            },
            style,
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
