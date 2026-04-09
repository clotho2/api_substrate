import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, Easing } from 'react-native';

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

  const animations = useRef(
    Array.from({ length: BAR_COUNT }, () => new Animated.Value(BASE_HEIGHT_RATIO))
  ).current;

  useEffect(() => {
    if (active) {
      const durations = [400, 550, 350, 480];
      const peaks = [0.9, 1.0, 0.75, 0.85];
      const delays = [0, 100, 50, 150];

      const loops = animations.map((anim, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.delay(delays[i]),
            Animated.sequence([
              Animated.timing(anim, {
                toValue: peaks[i] * MAX_HEIGHT_RATIO,
                duration: durations[i],
                easing: Easing.inOut(Easing.sin),
                useNativeDriver: false,
              }),
              Animated.timing(anim, {
                toValue: BASE_HEIGHT_RATIO,
                duration: durations[i],
                easing: Easing.inOut(Easing.sin),
                useNativeDriver: false,
              }),
            ]),
          ])
        )
      );

      loops.forEach((loop) => loop.start());
      return () => loops.forEach((loop) => loop.stop());
    } else {
      animations.forEach((anim) => {
        Animated.timing(anim, {
          toValue: BASE_HEIGHT_RATIO,
          duration: 200,
          useNativeDriver: false,
        }).start();
      });
    }
  }, [active]);

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      {animations.map((anim, i) => (
        <Animated.View
          key={i}
          style={[
            {
              width: barWidth,
              borderRadius: barWidth / 2,
              backgroundColor: color,
              marginHorizontal: gap / 2,
              height: anim.interpolate({
                inputRange: [0, 1],
                outputRange: [0, size],
              }),
            },
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
