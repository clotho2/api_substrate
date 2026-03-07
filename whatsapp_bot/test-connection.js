#!/usr/bin/env node
/**
 * Test Substrate API Connection
 * ==============================
 *
 * Verifies that the WhatsApp bot can connect to Assistant's substrate API
 * before starting the full bot.
 */

const axios = require('axios');
const dotenv = require('dotenv');

// Load environment
dotenv.config();

const SUBSTRATE_API_URL = process.env.SUBSTRATE_API_URL || 'http://localhost:8284';

async function testConnection() {
    console.log('\n' + '='.repeat(60));
    console.log('🧪 TESTING SUBSTRATE API CONNECTION');
    console.log('='.repeat(60));
    console.log(`   Target: ${SUBSTRATE_API_URL}`);
    console.log('='.repeat(60) + '\n');

    // Test 1: Health check
    console.log('Test 1: Health Check');
    console.log('   Endpoint: /api/chat/health');
    try {
        const healthResponse = await axios.get(
            `${SUBSTRATE_API_URL}/api/chat/health`,
            { timeout: 5000 }
        );

        if (healthResponse.status === 200) {
            console.log('   ✅ Health check passed');
            console.log('   Response:', JSON.stringify(healthResponse.data, null, 2));
        } else {
            console.log(`   ⚠️  Unexpected status: ${healthResponse.status}`);
        }
    } catch (error) {
        console.log('   ❌ Health check failed');
        if (error.code === 'ECONNREFUSED') {
            console.log('   Error: Connection refused - is the substrate API running?');
            console.log('   Expected: Flask server on', SUBSTRATE_API_URL);
            console.log('\n   Start the substrate:');
            console.log('   $ cd ../backend && python api/server.py\n');
        } else {
            console.log('   Error:', error.message);
        }
        process.exit(1);
    }

    // Test 2: Simple chat message
    console.log('\nTest 2: Simple Chat Message');
    console.log('   Endpoint: /api/chat');
    try {
        const chatResponse = await axios.post(
            `${SUBSTRATE_API_URL}/api/chat`,
            {
                message: 'Hello, this is a test from WhatsApp bot setup',
                session_id: 'whatsapp_test',
                stream: false
            },
            {
                timeout: 30000,
                headers: { 'Content-Type': 'application/json' }
            }
        );

        if (chatResponse.status === 200 && chatResponse.data.response) {
            console.log('   ✅ Chat endpoint working');
            console.log('   Response preview:', chatResponse.data.response.substring(0, 100) + '...');
            console.log('   Message ID:', chatResponse.data.message_id);
            console.log('   Session ID:', chatResponse.data.session_id);
        } else {
            console.log('   ⚠️  Unexpected response format');
            console.log('   Response:', chatResponse.data);
        }
    } catch (error) {
        console.log('   ❌ Chat test failed');
        if (error.response) {
            console.log('   Status:', error.response.status);
            console.log('   Error:', error.response.data);
        } else {
            console.log('   Error:', error.message);
        }
        process.exit(1);
    }

    // Test 3: Multimodal support check
    console.log('\nTest 3: Multimodal Support Check');
    console.log('   Checking if substrate supports image messages...');
    try {
        const features = await axios.get(
            `${SUBSTRATE_API_URL}/api/chat/health`,
            { timeout: 5000 }
        );

        const multimodalSupported = features.data.features?.multimodal;
        if (multimodalSupported) {
            console.log('   ✅ Multimodal (image) support: ENABLED');
        } else {
            console.log('   ⚠️  Multimodal support: DISABLED or PARTIAL');
        }
    } catch (error) {
        console.log('   ⚠️  Could not verify multimodal support');
    }

    // Success!
    console.log('\n' + '='.repeat(60));
    console.log('✅ ALL TESTS PASSED!');
    console.log('='.repeat(60));
    console.log('\nSubstrate API is ready for WhatsApp bot integration.');
    console.log('\nNext steps:');
    console.log('1. Configure user mapping (optional):');
    console.log('   $ cp user_mapping.json.example user_mapping.json');
    console.log('   $ nano user_mapping.json');
    console.log('\n2. Start the WhatsApp bot:');
    console.log('   $ npm start');
    console.log('\n3. Scan QR code with WhatsApp');
    console.log('='.repeat(60) + '\n');
}

// Run tests
testConnection().catch(error => {
    console.error('\n❌ Test suite failed:', error.message);
    process.exit(1);
});
