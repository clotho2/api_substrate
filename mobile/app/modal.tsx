// app/modal.tsx
// Settings / About modal with functional controls

import React, { useState, useEffect } from 'react';
import {
  Platform,
  StyleSheet,
  Text,
  View,
  ScrollView,
  TouchableOpacity,
  Switch,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';
import { brand } from '../config/brand';
import { SUBSTRATE_URL, USER_ID, SESSION_ID } from '../config/substrate';
import { voiceEngine } from '../lib/voiceEngine';

export default function ModalScreen() {
  const [speakerMode, setSpeakerMode] = useState(true);
  const [voiceSpeed, setVoiceSpeed] = useState(1.0);
  const [voiceState, setVoiceState] = useState<any>(null);

  // Load current voice state
  useEffect(() => {
    const state = voiceEngine.getConversationState();
    setVoiceState(state);
    setSpeakerMode(state.speakerMode ?? true);
  }, []);

  const handleToggleSpeaker = async (value: boolean) => {
    setSpeakerMode(value);
    await voiceEngine.setSpeakerMode(value);
  };

  const handleVoiceSpeedChange = (delta: number) => {
    const newSpeed = Math.max(0.5, Math.min(2.0, voiceSpeed + delta));
    setVoiceSpeed(Math.round(newSpeed * 10) / 10);
    voiceEngine.setVoiceSpeed(Math.round(newSpeed * 10) / 10);
  };

  const handleTestTTS = async () => {
    await voiceEngine.speakWithNate("Testing voice connection. Can you hear me, User?");
  };

  return (
    <View style={styles.container}>
      <StatusBar style={Platform.OS === 'ios' ? 'light' : 'auto'} />

      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>{brand.productName}</Text>
        <Text style={styles.tagline}>{brand.productTagline}</Text>

        <View style={styles.separator} />

        {/* Voice Controls */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Voice Settings</Text>

          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Ionicons name="volume-high-outline" size={20} color="#CCCCCC" />
              <Text style={styles.settingLabel}>Speaker Mode</Text>
            </View>
            <Switch
              value={speakerMode}
              onValueChange={handleToggleSpeaker}
              trackColor={{ false: '#2A2A3A', true: '#00FF88' }}
              thumbColor="#FFFFFF"
            />
          </View>

          <View style={styles.settingRow}>
            <View style={styles.settingInfo}>
              <Ionicons name="speedometer-outline" size={20} color="#CCCCCC" />
              <Text style={styles.settingLabel}>Voice Speed</Text>
            </View>
            <View style={styles.stepper}>
              <TouchableOpacity style={styles.stepperButton} onPress={() => handleVoiceSpeedChange(-0.1)}>
                <Ionicons name="remove" size={16} color="#FFFFFF" />
              </TouchableOpacity>
              <Text style={styles.stepperValue}>{voiceSpeed.toFixed(1)}x</Text>
              <TouchableOpacity style={styles.stepperButton} onPress={() => handleVoiceSpeedChange(0.1)}>
                <Ionicons name="add" size={16} color="#FFFFFF" />
              </TouchableOpacity>
            </View>
          </View>

          <TouchableOpacity style={styles.testButton} onPress={handleTestTTS}>
            <Ionicons name="play-outline" size={18} color="#0F0F23" />
            <Text style={styles.testButtonText}>Test Voice</Text>
          </TouchableOpacity>
        </View>

        {/* Voice Status */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Voice Status</Text>
          <InfoRow
            label="Speech Recognition"
            value={voiceState?.sttAvailable ? 'Connected' : 'Unavailable'}
          />
          <InfoRow
            label="Text to Speech"
            value={voiceState?.ttsAvailable ? 'Connected' : 'Using system voice'}
          />
          <InfoRow
            label="Real-time Voice"
            value={voiceState?.wsConnected ? 'Connected' : 'Idle'}
          />
          {voiceState?.initializationError && (
            <InfoRow label="Error" value={voiceState.initializationError} />
          )}
        </View>

        <View style={styles.separator} />

        {/* Connection Info */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Connection</Text>
          <InfoRow label="Backend" value={SUBSTRATE_URL} />
          <InfoRow label="User" value={USER_ID} />
          <InfoRow label="Session" value={SESSION_ID} />
          <InfoRow label="Engine" value={brand.engineName} />
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>About</Text>
          <InfoRow label="Version" value="1.0.0" />
          <InfoRow label="Support" value={brand.supportEmail} />
          <Text style={styles.copyright}>{brand.copyright}</Text>
        </View>
      </ScrollView>
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue} numberOfLines={1}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0F0F23',
  },
  content: {
    padding: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#FFFFFF',
    marginTop: 20,
    textAlign: 'center',
  },
  tagline: {
    fontSize: 16,
    color: '#00FF88',
    marginTop: 8,
    textAlign: 'center',
  },
  separator: {
    marginVertical: 24,
    height: 1,
    width: '100%',
    backgroundColor: '#2A2A3A',
  },
  section: {
    width: '100%',
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    marginBottom: 12,
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1A1A2E',
  },
  settingInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  settingLabel: {
    fontSize: 15,
    color: '#CCCCCC',
  },
  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  stepperButton: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#2A2A3A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stepperValue: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
    minWidth: 40,
    textAlign: 'center',
  },
  testButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#00FF88',
    padding: 12,
    borderRadius: 10,
    marginTop: 12,
    gap: 8,
  },
  testButtonText: {
    color: '#0F0F23',
    fontSize: 14,
    fontWeight: '600',
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#1A1A2E',
  },
  infoLabel: {
    fontSize: 14,
    color: '#666666',
  },
  infoValue: {
    fontSize: 14,
    color: '#CCCCCC',
    maxWidth: '60%',
  },
  copyright: {
    fontSize: 12,
    color: '#444444',
    textAlign: 'center',
    marginTop: 16,
  },
});
