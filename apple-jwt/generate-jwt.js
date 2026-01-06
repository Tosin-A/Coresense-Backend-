const jwt = require('jsonwebtoken');
const fs = require('fs');

// === REPLACE THESE ===
const teamId = '6C383NJ99X';        // Your 10-char Team ID
const keyId = '3RVGPKK5M8';         // Your 10-char Key ID from filename
const serviceId = 'com.coresense.app'; // Your Service ID (Client ID) for 'sub' claim
                                      // This is REQUIRED for Supabase Apple Sign In
                                      // Should match the Service ID you created in Apple Developer Portal
// =====================

// Read the .p8 file - make sure filename matches!
let privateKeyRaw = fs.readFileSync(`AuthKey_${keyId}.p8`, 'utf8').trim();

// Wrap in PEM format if not already wrapped (Apple's .p8 files need this)
if (!privateKeyRaw.includes('-----BEGIN')) {
  // Preserve any existing line breaks in the key content
  const keyContent = privateKeyRaw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  privateKeyRaw = `-----BEGIN PRIVATE KEY-----\n${keyContent}\n-----END PRIVATE KEY-----`;
}

const privateKey = privateKeyRaw;

// Create the JWT client secret for Apple Sign In
// For Sign in with Apple, use 'https://appleid.apple.com' as audience
const now = Math.floor(Date.now() / 1000);
const payload = {
  iss: teamId,
  iat: now,
  exp: now + 15777000, // 6 months (15777000 seconds = ~6 months)
  aud: 'https://appleid.apple.com'
};

// 'sub' should be Service ID (Client ID) for Apple Sign In client secrets
// If serviceId is not provided, use teamId as fallback
if (serviceId) {
  payload.sub = serviceId;
} else {
  payload.sub = teamId;
}

const token = jwt.sign(
  payload,
  privateKey,
  {
    algorithm: 'ES256',
    header: {
      alg: 'ES256',
      kid: keyId
    }
  }
);

console.log('\n=== COPY THIS JWT TO SUPABASE SECRET KEY FIELD ===');
console.log(token);
console.log('\n=== VERIFICATION INFO ===');
console.log(`Team ID (iss): ${teamId}`);
console.log(`Key ID (kid): ${keyId}`);
console.log(`Subject (sub): ${payload.sub}`);
console.log(`Expires: ${new Date(payload.exp * 1000).toISOString()}`);
console.log(`Token length: ${token.length} chars\n`);

// Also provide the raw .p8 file option in case Supabase expects that instead
console.log('=== ALTERNATIVE: If Supabase expects .p8 file content, use this ===');
console.log('(Copy the entire content below including BEGIN/END lines)\n');
console.log(privateKey);
console.log('\n');