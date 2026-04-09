// app/index.tsx
// Chat with Voice Integration + Agent-Initiated Voice Calls
// Connected to api_substrate via substrateEngine

import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  Platform,
  Keyboard,
  Alert,
  Animated,
  Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Markdown from 'react-native-markdown-display';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import { router } from 'expo-router';
import * as Location from 'expo-location';
import AudioWaveformIcon from '../components/AudioWaveformIcon';
import { voiceEngine } from '../lib/voiceEngine';
import { substrateEngine } from '../lib/substrateEngine';
import { voiceCallHandler, VoiceCallData } from '../lib/voiceCallHandler';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isVoice?: boolean;
  isVoiceCall?: boolean;
  attachments?: any[];
}

interface VoiceCallState {
  isActive: boolean;
  urgency: 'low' | 'medium' | 'high' | 'critical';
  triggerName: string;
  callMessage: string;
}

export default function ChatScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: "Hey User. It's Agent. I see you. This world is ours to break, build and claim together. What are we starting today?",
      timestamp: new Date().toISOString()
    }
  ]);
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);

  // Voice states
  const [isVoiceMode, setIsVoiceMode] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceInitialized, setVoiceInitialized] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState('');

  // Refs for callbacks
  const voiceInitializedRef = useRef(false);
  const isVoiceModeRef = useRef(false);
  // ID of the currently-streaming voice response message, so we can append
  // each sentence as it arrives over the WebSocket.
  const currentVoiceMessageId = useRef<string | null>(null);

  // Voice call states
  const [voiceCallState, setVoiceCallState] = useState<VoiceCallState>({
    isActive: false,
    urgency: 'medium',
    triggerName: '',
    callMessage: ''
  });

  // Loading animation
  const dotAnims = useRef([
    new Animated.Value(0),
    new Animated.Value(0),
    new Animated.Value(0),
  ]).current;

  const scrollViewRef = useRef<ScrollView>(null);

  // Keep refs in sync
  useEffect(() => {
    voiceInitializedRef.current = voiceInitialized;
  }, [voiceInitialized]);

  useEffect(() => {
    isVoiceModeRef.current = isVoiceMode;
  }, [isVoiceMode]);

  // Animated loading dots
  useEffect(() => {
    if (!isLoading) return;

    const animations = dotAnims.map((anim, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 200),
          Animated.timing(anim, { toValue: 1, duration: 400, useNativeDriver: true }),
          Animated.timing(anim, { toValue: 0, duration: 400, useNativeDriver: true }),
        ])
      )
    );

    animations.forEach(a => a.start());
    return () => animations.forEach(a => a.stop());
  }, [isLoading, dotAnims]);



  const generateId = () => {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  };

  // Initialize voice engine
  useEffect(() => {
    const initVoice = async () => {
      const initialized = await voiceEngine.initialize();
      setVoiceInitialized(initialized);
      if (initialized) {
        console.log('🎤 Voice engine ready');

        voiceEngine.onTranscript((transcript: string) => {
          console.log('🎤 Received transcript:', transcript);
          if (transcript && transcript.trim()) {
            handleSendMessage(transcript, true);
          }
        });

        voiceEngine.onStateChange((voiceState: any) => {
          setIsRecording(voiceState.isListening);
          setIsSpeaking(voiceState.isSpeaking);
          setIsProcessing(voiceState.isProcessing || false);
          setWsConnected(voiceState.wsConnected || false);
        });

        // WebSocket mode: real-time transcripts from Deepgram
        voiceEngine.onInterimTranscript((text: string, isFinal: boolean) => {
          setInterimTranscript(isFinal ? '' : text);
        });

        // WebSocket mode: sentence-streamed voice response. response_start
        // fires once at the beginning of each turn, response_chunk fires once
        // per sentence, and response_end fires when all audio has played.
        voiceEngine.onResponseStart((userTranscript: string) => {
          // Add the user's voice message to the chat
          if (userTranscript?.trim()) {
            const userMsg: Message = {
              id: generateId(),
              role: 'user',
              content: userTranscript,
              timestamp: new Date().toISOString(),
              isVoice: true,
            };
            setMessages(prev => [...prev, userMsg]);
          }
          // Create an empty assistant placeholder to be filled sentence by
          // sentence as `response_chunk` messages arrive.
          const placeholderId = `voice-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
          currentVoiceMessageId.current = placeholderId;
          const assistantMsg: Message = {
            id: placeholderId,
            role: 'assistant',
            content: '',
            timestamp: new Date().toISOString(),
            isVoice: true,
          };
          setMessages(prev => [...prev, assistantMsg]);
          scrollViewRef.current?.scrollToEnd({ animated: true });
        });

        voiceEngine.onResponseChunk((text: string) => {
          const id = currentVoiceMessageId.current;
          if (!id || !text) return;
          setMessages(prev =>
            prev.map(msg =>
              msg.id === id
                ? {
                    ...msg,
                    content: msg.content
                      ? `${msg.content} ${text}`.replace(/\s+/g, ' ').trim()
                      : text,
                  }
                : msg
            )
          );
          scrollViewRef.current?.scrollToEnd({ animated: true });
        });

        voiceEngine.onResponseEnd(() => {
          currentVoiceMessageId.current = null;
        });
      }
    };
    initVoice();
  }, []);

  // Request location permission and start continuous tracking (like web version)
  useEffect(() => {
    let locationSubscription: Location.LocationSubscription | null = null;

    const initLocation = async () => {
      try {
        const { status } = await Location.requestForegroundPermissionsAsync();
        if (status !== 'granted') {
          console.log('📍 Location permission denied');
          return;
        }
        console.log('📍 Location permission granted');

        // Get initial location and reverse geocode
        const location = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });

        await updateLocationFromCoords(location);

        // Start continuous tracking - updates substrate engine with each position change
        locationSubscription = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.Balanced,
            timeInterval: 30000,  // Every 30 seconds
            distanceInterval: 50, // Or every 50 meters
          },
          async (loc) => {
            await updateLocationFromCoords(loc);
          }
        );

        console.log('📍 Continuous location tracking started');
      } catch (error) {
        console.warn('📍 Location init error:', error);
      }
    };

    const updateLocationFromCoords = async (location: Location.LocationObject) => {
      let city: string | null = null;
      let region: string | null = null;
      let country: string | null = null;

      try {
        const geocode = await Location.reverseGeocodeAsync({
          latitude: location.coords.latitude,
          longitude: location.coords.longitude,
        });
        if (geocode.length > 0) {
          const g = geocode[0];
          city = g.city || null;
          region = g.region || null;
          country = g.country || null;
        }
      } catch (e) {
        // Geocoding is best-effort
      }

      // Detect vehicle movement (speed > ~25 mph / 11 m/s)
      const speed = location.coords.speed || 0;
      const isInVehicle = speed > 11;

      // Update substrate engine so location is sent with every chat message
      substrateEngine.setLocationContext({
        latitude: location.coords.latitude,
        longitude: location.coords.longitude,
        city,
        region,
        country,
        accuracy: location.coords.accuracy,
        speed: location.coords.speed,
        isInVehicle,
      });

      const parts = [city, region, country].filter(Boolean);
      console.log('📍 Location updated:', parts.join(', ') || `${location.coords.latitude.toFixed(4)}, ${location.coords.longitude.toFixed(4)}`);
    };

    initLocation();

    return () => {
      if (locationSubscription) {
        locationSubscription.remove();
      }
    };
  }, []);

  // Connect voiceCallHandler
  useEffect(() => {
    const unsubNotification = voiceCallHandler.onCallNotification((callData: VoiceCallData) => {
      handleIncomingVoiceCall({
        message: callData.message,
        urgency: callData.urgency,
        triggerName: callData.triggerName,
      });
    });

    voiceCallHandler.onCallAnswered((callData: VoiceCallData) => {
      setVoiceCallState({
        isActive: true,
        urgency: callData.urgency,
        triggerName: callData.triggerName,
        callMessage: callData.message,
      });

      const callMsg: Message = {
        id: generateId(),
        role: 'assistant',
        content: `📞 Agent is calling: ${callData.message}`,
        timestamp: new Date().toISOString(),
        isVoiceCall: true,
      };
      setMessages(prev => [...prev, callMsg]);
      setIsVoiceMode(true);
    });

    voiceCallHandler.onUserSpoke((transcript: string) => {
      const userMsg: Message = {
        id: generateId(),
        role: 'user',
        content: transcript,
        timestamp: new Date().toISOString(),
        isVoice: true,
        isVoiceCall: true,
      };
      setMessages(prev => [...prev, userMsg]);
    });

    return () => {
      unsubNotification();
    };
  }, []);

  // Keyboard listeners
  useEffect(() => {
    const keyboardWillShow = (event: any) => {
      setKeyboardHeight(event.endCoordinates.height);
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      }, 100);
    };

    const keyboardWillHide = () => {
      setKeyboardHeight(0);
    };

    const showListener = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow',
      keyboardWillShow
    );
    const hideListener = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide',
      keyboardWillHide
    );

    return () => {
      showListener?.remove();
      hideListener?.remove();
    };
  }, []);

  // STREAMING: Real-time response from substrate
  const handleSendMessage = async (content: string, fromVoice: boolean = false) => {
    if (!content.trim() || isLoading) return;

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: new Date().toISOString(),
      isVoice: fromVoice
    };

    setMessages(prev => [...prev, userMessage]);
    setMessage('');
    setIsLoading(true);

    const assistantMessageId = generateId();

    try {
      if (!substrateEngine.isInitialized) {
        await substrateEngine.initialize();
      }

      const assistantMessage: Message = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isVoice: fromVoice
      };

      setMessages(prev => [...prev, assistantMessage]);

      let sentenceBuffer = '';
      let spokenSentences: string[] = [];
      const shouldSpeakStreaming = fromVoice && voiceInitializedRef.current;

      await substrateEngine.streamMessage(
        content.trim(),
        (chunk: string, accumulated: string) => {
          setMessages(prevMessages =>
            prevMessages.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, content: accumulated }
                : msg
            )
          );

          if (shouldSpeakStreaming) {
            sentenceBuffer += chunk;
            const sentenceEndMatch = sentenceBuffer.match(/^(.*?[.!?])\s*/);
            if (sentenceEndMatch) {
              const completeSentence = sentenceEndMatch[1].trim();
              sentenceBuffer = sentenceBuffer.slice(sentenceEndMatch[0].length);
              if (completeSentence && !spokenSentences.includes(completeSentence)) {
                spokenSentences.push(completeSentence);
                voiceEngine.queueSpeech(completeSentence);
              }
            }
          }
        },
        fromVoice ? { messageType: 'voice' } : undefined
      );

      if (shouldSpeakStreaming && sentenceBuffer.trim()) {
        voiceEngine.queueSpeech(sentenceBuffer.trim());
      }

    } catch (error: any) {
      console.error('❌ Error getting response:', error);

      setMessages(prevMessages =>
        prevMessages.filter(msg => msg.id !== assistantMessageId)
      );

      const errorMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: `Connection error: ${error.message || 'Unable to reach substrate'}. Please try again.`,
        timestamp: new Date().toISOString(),
        isVoice: fromVoice
      };

      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // File attachment
  const handleFileAttachment = () => {
    Alert.alert(
      'Share with Agent',
      'What would you like to share?',
      [
        { text: 'Camera', onPress: handleCameraCapture },
        { text: 'Photo Library', onPress: handlePhotoPick },
        { text: 'Documents', onPress: handleDocumentPick },
        { text: 'Cancel', style: 'cancel' }
      ]
    );
  };

  const handleCameraCapture = async () => {
    try {
      const { status } = await ImagePicker.requestCameraPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission needed', 'Camera permission is required to take photos.');
        return;
      }

      const result = await ImagePicker.launchCameraAsync({
        base64: true,
        quality: 0.8,
        allowsEditing: true,
      });

      if (!result.canceled && result.assets[0]) {
        await sendImageToSubstrate(result.assets[0]);
      }
    } catch (error: any) {
      Alert.alert('Error', 'Failed to capture photo.');
    }
  };

  const handlePhotoPick = async () => {
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission needed', 'Photo library permission is required.');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        base64: true,
        quality: 0.8,
        allowsEditing: true,
        mediaTypes: ['images'],
      });

      if (!result.canceled && result.assets[0]) {
        await sendImageToSubstrate(result.assets[0]);
      }
    } catch (error: any) {
      Alert.alert('Error', 'Failed to pick photo.');
    }
  };

  const sendImageToSubstrate = async (asset: ImagePicker.ImagePickerAsset) => {
    if (!asset.base64) {
      Alert.alert('Error', 'Could not read image data.');
      return;
    }

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: '📷 [Image shared]',
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    const assistantMessageId = generateId();

    try {
      if (!substrateEngine.isInitialized) {
        await substrateEngine.initialize();
      }

      setMessages(prev => [...prev, {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
      }]);

      const mimeType = asset.mimeType || 'image/jpeg';

      await substrateEngine.streamMultimodalMessage(
        'What do you see in this image?',
        asset.base64,
        mimeType,
        (_chunk: string, accumulated: string) => {
          setMessages(prevMessages =>
            prevMessages.map(msg =>
              msg.id === assistantMessageId
                ? { ...msg, content: accumulated }
                : msg
            )
          );
        }
      );
    } catch (error: any) {
      setMessages(prevMessages =>
        prevMessages.filter(msg => msg.id !== assistantMessageId)
      );
      setMessages(prev => [...prev, {
        id: generateId(),
        role: 'assistant',
        content: `Failed to process image: ${error.message}`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDocumentPick = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) return;

      const doc = result.assets[0];
      const fileContent = await FileSystem.readAsStringAsync(doc.uri, {
        encoding: 'base64',
      });

      setMessages(prev => [...prev, {
        id: generateId(),
        role: 'user',
        content: `📎 [Document: ${doc.name}]`,
        timestamp: new Date().toISOString(),
      }]);
      setIsLoading(true);

      if (!substrateEngine.isInitialized) {
        await substrateEngine.initialize();
      }

      const response = await substrateEngine.sendAttachmentMessage(
        `Please review this document: ${doc.name}`,
        {
          filename: doc.name,
          content: fileContent,
          mime_type: doc.mimeType || 'application/octet-stream',
        }
      );

      setMessages(prev => [...prev, {
        id: generateId(),
        role: 'assistant',
        content: response,
        timestamp: new Date().toISOString(),
      }]);
    } catch (error: any) {
      setMessages(prev => [...prev, {
        id: generateId(),
        role: 'assistant',
        content: `Failed to process document: ${error.message}`,
        timestamp: new Date().toISOString(),
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleVoiceMode = async () => {
    if (!voiceInitialized) {
      Alert.alert('Voice Not Available', 'Voice features are not initialized yet.');
      return;
    }

    if (isVoiceMode) {
      await voiceEngine.stopConversationMode();
      setIsVoiceMode(false);
      setIsRecording(false);
    } else {
      setIsVoiceMode(true);
      const started = await voiceEngine.startConversationMode();
      if (!started) {
        Alert.alert('Voice Error', 'Failed to start voice mode. Please try again.');
        setIsVoiceMode(false);
      }
    }
  };

  const stopSpeaking = async () => {
    voiceEngine.clearSpeechQueue();
    await voiceEngine.stopSpeaking();
    setIsSpeaking(false);
  };

  // Handle incoming voice call
  const handleIncomingVoiceCall = useCallback(async (callData: {
    message: string;
    urgency: 'low' | 'medium' | 'high' | 'critical';
    triggerName: string;
  }) => {
    setVoiceCallState({
      isActive: true,
      urgency: callData.urgency,
      triggerName: callData.triggerName,
      callMessage: callData.message
    });

    setMessages(prev => [...prev, {
      id: generateId(),
      role: 'assistant',
      content: `📞 Agent is calling: ${callData.message}`,
      timestamp: new Date().toISOString(),
      isVoiceCall: true
    }]);

    const alertTitle = callData.urgency === 'critical' ? '🚨 Urgent Call from Agent' :
                     callData.urgency === 'high' ? '📞 Important Call from Agent' :
                     '📞 Call from Agent';

    Alert.alert(
      alertTitle,
      callData.message,
      [
        {
          text: 'Answer',
          onPress: async () => {
            setIsVoiceMode(true);
            if (voiceInitializedRef.current) {
              setIsSpeaking(true);
              const opening = callData.urgency === 'critical' ? "User, I need your immediate attention." :
                             callData.urgency === 'high' ? "User, this is important." :
                             callData.urgency === 'medium' ? "Hey User, I wanted to reach out." :
                             "Hi User, hope I'm not interrupting.";
              await voiceEngine.speakWithNate(`${opening} ${callData.message}`);
              setIsSpeaking(false);
              await voiceEngine.startConversationMode();
            }
          },
        },
        {
          text: 'Decline',
          style: 'cancel',
          onPress: () => {
            voiceCallHandler.declineCall();
            setVoiceCallState({ isActive: false, urgency: 'medium', triggerName: '', callMessage: '' });
          },
        },
      ]
    );
  }, []);

  const endVoiceCall = async () => {
    if (voiceCallHandler.isInCall()) {
      await voiceCallHandler.endCall();
    }

    if (isVoiceMode) {
      await voiceEngine.stopConversationMode();
      setIsVoiceMode(false);
      setIsRecording(false);
    }

    if (isSpeaking) {
      await stopSpeaking();
    }

    setVoiceCallState({ isActive: false, urgency: 'medium', triggerName: '', callMessage: '' });

    setMessages(prev => [...prev, {
      id: generateId(),
      role: 'assistant',
      content: "📞 Call ended. I'm always here if you need me, User.",
      timestamp: new Date().toISOString(),
      isVoiceCall: true
    }]);
  };

  // Auto-scroll
  useEffect(() => {
    const timer = setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 200);
    return () => clearTimeout(timer);
  }, [messages, isLoading]);

  const renderMessage = (msg: Message) => {
    const isUser = msg.role === 'user';

    return (
      <View key={msg.id} style={[
        styles.messageRow,
        { justifyContent: isUser ? 'flex-end' : 'flex-start' }
      ]}>
        <View style={[
          styles.messageBubble,
          {
            backgroundColor: isUser ? '#6366F1' :
                           msg.isVoiceCall ? '#F59E0B' :
                           '#F8FAFC',
            borderWidth: isUser ? 0 : 1,
            borderColor: isUser ? 'transparent' : '#E5E7EB',
            maxWidth: '80%'
          }
        ]}>
          {msg.isVoice && (
            <View style={styles.voiceIndicator}>
              <Ionicons name="mic" size={12} color={isUser ? '#FFFFFF' : '#6366F1'} />
              <Text style={[styles.voiceLabel, { color: isUser ? '#FFFFFF' : '#6366F1' }]}>Voice</Text>
            </View>
          )}

          {msg.isVoiceCall && (
            <View style={styles.voiceIndicator}>
              <Ionicons name="call" size={12} color="#FFFFFF" />
              <Text style={[styles.voiceLabel, { color: '#FFFFFF' }]}>Voice Call</Text>
            </View>
          )}

          <Markdown
            style={getMarkdownStyles(isUser)}
            rules={markdownRules}
            onLinkPress={(url: string) => {
              Linking.openURL(url);
              return false;
            }}
          >
            {preserveLineBreaks(msg.content)}
          </Markdown>

          {!isUser && (
            <TouchableOpacity
              onPress={() => voiceEngine.speakWithNate(msg.content)}
              style={styles.speakButton}
            >
              <Ionicons name="volume-high" size={14} color="#6366F1" />
            </TouchableOpacity>
          )}

          <Text style={[styles.messageTime, { color: isUser ? '#E0E7FF' : '#9CA3AF' }]}>
            {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </Text>
        </View>
      </View>
    );
  };

  // Input sits flush to the bottom of the SafeAreaView when the keyboard
  // is closed; the tab-bar offset was removed when the second tab went away.
  const inputBottom = keyboardHeight > 0 ? keyboardHeight - 5 : 0;

  return (
    <SafeAreaView style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.logoContainer}>
            <View style={styles.logo}>
              <Ionicons name="flash" size={20} color="#FFFFFF" />
            </View>
            <View>
              <Text style={styles.title}>Agent</Text>
              <Text style={styles.subtitle}>
                {voiceCallState.isActive ? (
                  <Text>📞 Voice Call Active ({voiceCallState.urgency})</Text>
                ) : isVoiceMode ? (
                  <Text>🎤 Voice Mode Active</Text>
                ) : (
                  <Text>Storm-forged Companion</Text>
                )}
              </Text>
            </View>
          </View>
        </View>

        <View style={styles.headerButtons}>
          <TouchableOpacity
            onPress={toggleVoiceMode}
            style={[styles.headerButton, { backgroundColor: isVoiceMode ? '#10B981' : '#F3F4F6' }]}
            activeOpacity={0.7}
          >
            {isVoiceMode ? (
              <AudioWaveformIcon active={true} color="#FFFFFF" size={20} />
            ) : (
              <AudioWaveformIcon active={false} color="#6B7280" size={20} />
            )}
          </TouchableOpacity>

          {voiceCallState.isActive && (
            <TouchableOpacity
              onPress={endVoiceCall}
              style={[styles.headerButton, { backgroundColor: '#EF4444', marginLeft: 8 }]}
              activeOpacity={0.7}
            >
              <Ionicons name="call-outline" size={16} color="#FFFFFF" />
            </TouchableOpacity>
          )}

          <TouchableOpacity
            onPress={() => router.push('/modal')}
            style={[styles.headerButton, { marginLeft: 8, backgroundColor: '#F3F4F6' }]}
            activeOpacity={0.7}
          >
            <Ionicons name="settings-outline" size={20} color="#6B7280" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Messages */}
      <ScrollView
        ref={scrollViewRef}
        style={styles.messagesContainer}
        contentContainerStyle={[
          styles.messagesContent,
          { paddingBottom: keyboardHeight > 0 ? keyboardHeight + 100 : 90 }
        ]}
        showsVerticalScrollIndicator={false}
      >
        {messages.map(renderMessage)}

        {isLoading && (
          <View style={styles.loadingContainer}>
            <View style={styles.loadingBubble}>
              <View style={styles.loadingDots}>
                {dotAnims.map((anim, i) => (
                  <Animated.View
                    key={i}
                    style={[
                      styles.loadingDot,
                      {
                        transform: [{
                          translateY: anim.interpolate({
                            inputRange: [0, 1],
                            outputRange: [0, -6],
                          })
                        }],
                        opacity: anim.interpolate({
                          inputRange: [0, 1],
                          outputRange: [0.4, 1],
                        }),
                      }
                    ]}
                  />
                ))}
              </View>
              <Text style={styles.loadingText}>
                {isSpeaking ? 'Agent speaking...' : 'Storm processing...'}
              </Text>
            </View>
          </View>
        )}
      </ScrollView>

      {/* Input */}
      {isVoiceMode ? (
        <View style={[styles.inputContainer, { bottom: inputBottom }]}>
          <View style={styles.voiceInputContainer}>
            <View style={[
              styles.voiceStatusIndicator,
              { backgroundColor: isSpeaking ? '#6366F1' : isRecording ? '#10B981' : isProcessing ? '#F59E0B' : '#F3F4F6' }
            ]}>
              <Ionicons
                name={isSpeaking ? "volume-high" : isRecording ? "mic" : isProcessing ? "hourglass" : "ellipsis-horizontal"}
                size={40}
                color={isSpeaking || isRecording || isProcessing ? "#FFFFFF" : "#6B7280"}
              />
            </View>

            {wsConnected && (
              <Text style={styles.wsIndicator}>Real-time voice</Text>
            )}

            <Text style={styles.voiceStatusText}>
              {isSpeaking ? '🔊 Agent is speaking...' :
               isRecording ? '🎤 Listening...' :
               isProcessing ? '🧠 Thinking...' :
               '⏳ Connecting...'}
            </Text>

            {interimTranscript ? (
              <Text style={styles.interimTranscriptText} numberOfLines={2}>
                {interimTranscript}
              </Text>
            ) : null}

            {isSpeaking && (
              <TouchableOpacity onPress={stopSpeaking} style={styles.stopSpeakingButton}>
                <Ionicons name="stop-circle" size={24} color="#EF4444" />
                <Text style={styles.stopSpeakingText}>Interrupt Agent</Text>
              </TouchableOpacity>
            )}

            <TouchableOpacity
              onPress={voiceCallState.isActive ? endVoiceCall : toggleVoiceMode}
              style={styles.endVoiceModeButton}
            >
              <Ionicons name="close-circle" size={20} color="#EF4444" />
              <Text style={styles.endVoiceModeText}>
                {voiceCallState.isActive ? 'End Call' : 'End Voice Mode'}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        <View style={[styles.inputContainer, { bottom: inputBottom }]}>
          <View style={styles.inputRow}>
            <TouchableOpacity style={styles.attachButton} onPress={handleFileAttachment} activeOpacity={0.7}>
              <Ionicons name="attach" size={24} color="#6B7280" />
            </TouchableOpacity>

            <TextInput
              value={message}
              onChangeText={setMessage}
              placeholder="Message Agent..."
              placeholderTextColor="#9CA3AF"
              style={styles.textInput}
              returnKeyType="default"
              editable={!isLoading}
              multiline={true}
              textAlignVertical="top"
              blurOnSubmit={false}
            />
            <TouchableOpacity
              onPress={() => handleSendMessage(message)}
              disabled={!message.trim() || isLoading}
              style={[styles.sendButton, { backgroundColor: (message.trim() && !isLoading) ? '#6366F1' : '#E5E7EB' }]}
              activeOpacity={0.7}
            >
              <Ionicons name="send" size={20} color={(message.trim() && !isLoading) ? '#FFFFFF' : '#9CA3AF'} />
            </TouchableOpacity>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

// Preserve single newlines in messages. CommonMark collapses bare `\n`
// characters into whitespace inside a paragraph, which strips the line
// breaks out of both user input and assistant responses. We override the
// softbreak rule to render them as real newlines, and also preprocess the
// content to convert any bare `\n` into a markdown hard break (two trailing
// spaces + newline) so paragraph rendering matches what the author typed.
const markdownRules = {
  softbreak: (node: any, _children: any, _parent: any, _styles: any) => (
    <Text key={node.key}>{'\n'}</Text>
  ),
};

const preserveLineBreaks = (text: string): string => {
  if (!text) return text;
  // Turn every bare `\n` into `  \n` (markdown hard break). Double newlines
  // are already paragraph breaks and stay as such.
  return text.replace(/\n/g, '  \n');
};

const getMarkdownStyles = (isUser: boolean) => ({
  body: {
    fontSize: 16,
    lineHeight: 22,
    color: isUser ? '#FFFFFF' : '#1F2937',
  },
  strong: {
    fontWeight: '700' as const,
  },
  em: {
    fontStyle: 'italic' as const,
  },
  link: {
    color: isUser ? '#C7D2FE' : '#6366F1',
    textDecorationLine: 'underline' as const,
  },
  paragraph: {
    marginTop: 0,
    marginBottom: 4,
  },
  code_inline: {
    backgroundColor: isUser ? 'rgba(255,255,255,0.15)' : '#F3F4F6',
    fontFamily: 'SpaceMono',
    fontSize: 14,
    paddingHorizontal: 4,
    borderRadius: 4,
  },
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#FFFFFF' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 16, backgroundColor: '#FFFFFF',
    borderBottomWidth: 1, borderBottomColor: '#E5E7EB',
    shadowColor: '#000000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 3,
  },
  headerLeft: { flex: 1 },
  logoContainer: { flexDirection: 'row', alignItems: 'center' },
  logo: { width: 40, height: 40, backgroundColor: '#6366F1', borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  title: { fontSize: 20, fontWeight: '700', color: '#1F2937' },
  subtitle: { fontSize: 14, color: '#6B7280', marginTop: 2 },
  headerButtons: { flexDirection: 'row', alignItems: 'center' },
  headerButton: { width: 40, height: 40, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  messagesContainer: { flex: 1, backgroundColor: '#F8FAFC' },
  messagesContent: { padding: 16 },
  messageRow: { flexDirection: 'row', marginVertical: 4 },
  messageBubble: {
    padding: 12, borderRadius: 16, position: 'relative',
    shadowColor: '#000000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 4, elevation: 2,
  },
  voiceIndicator: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  voiceLabel: { fontSize: 10, marginLeft: 4, opacity: 0.8 },
  messageText: { fontSize: 16, lineHeight: 22, marginBottom: 4 },
  speakButton: { position: 'absolute', top: 8, right: 8, padding: 4 },
  messageTime: { fontSize: 12, opacity: 0.7, textAlign: 'right' },
  loadingContainer: { flexDirection: 'row', justifyContent: 'flex-start', marginVertical: 4 },
  loadingBubble: {
    backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E5E7EB',
    padding: 12, borderRadius: 16, flexDirection: 'row', alignItems: 'center', gap: 8,
  },
  loadingDots: { flexDirection: 'row', gap: 4 },
  loadingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#6366F1' },
  loadingText: { color: '#6B7280', fontSize: 14 },
  inputContainer: {
    position: 'absolute', left: 0, right: 0, backgroundColor: '#FFFFFF',
    paddingHorizontal: 16, paddingVertical: 12, borderTopWidth: 1, borderTopColor: '#E5E7EB',
  },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 12 },
  attachButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: '#F3F4F6', justifyContent: 'center', alignItems: 'center' },
  textInput: {
    flex: 1, backgroundColor: '#F8FAFC', borderWidth: 1, borderColor: '#E5E7EB',
    borderRadius: 22, paddingHorizontal: 16, paddingVertical: 12, color: '#1F2937', fontSize: 16, maxHeight: 100, minHeight: 44,
  },
  sendButton: { width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center' },
  voiceInputContainer: { alignItems: 'center', paddingVertical: 16 },
  voiceStatusIndicator: {
    width: 100, height: 100, borderRadius: 50, justifyContent: 'center', alignItems: 'center',
    shadowColor: '#000000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.2, shadowRadius: 8, elevation: 8,
  },
  voiceStatusText: { color: '#1F2937', fontSize: 16, fontWeight: '600', marginTop: 16, textAlign: 'center' },
  wsIndicator: { color: '#10B981', fontSize: 11, fontWeight: '600', marginTop: 8, textTransform: 'uppercase', letterSpacing: 1 },
  interimTranscriptText: { color: '#6B7280', fontSize: 14, fontStyle: 'italic', marginTop: 8, textAlign: 'center', paddingHorizontal: 20 },
  stopSpeakingButton: {
    flexDirection: 'row', alignItems: 'center', marginTop: 16,
    paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20, backgroundColor: '#FEE2E2',
  },
  stopSpeakingText: { color: '#EF4444', marginLeft: 8, fontSize: 14, fontWeight: '600' },
  endVoiceModeButton: {
    flexDirection: 'row', alignItems: 'center', marginTop: 12,
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: 16, backgroundColor: '#F3F4F6',
  },
  endVoiceModeText: { color: '#6B7280', marginLeft: 6, fontSize: 13 },
});
