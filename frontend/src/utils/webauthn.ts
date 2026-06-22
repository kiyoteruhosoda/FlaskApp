// 最小限の WebAuthn(パスキー)補助。外部依存なしで base64url 変換と
// navigator.credentials.get の呼び出し・サーバー送信用シリアライズを行う。
// バックエンドは py_webauthn 互換の JSON(base64url 文字列)を期待する。

export function base64urlToBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/');
  const pad = padded.length % 4 === 0 ? '' : '='.repeat(4 - (padded.length % 4));
  const binary = atob(padded + pad);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

export function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function isPasskeySupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.PublicKeyCredential !== 'undefined' &&
    !!navigator.credentials
  );
}

interface RegisterOptions {
  challenge: string;
  timeout?: number;
  rp?: { id?: string; name: string };
  user: { id: string; name: string; displayName: string };
  pubKeyCredParams: Array<{ type: 'public-key'; alg: number }>;
  attestation?: AttestationConveyancePreference;
  excludeCredentials?: Array<{ id: string; type: 'public-key' }>;
  authenticatorSelection?: AuthenticatorSelectionCriteria;
}

/**
 * サーバーが返した登録オプション(base64url)を WebAuthn 用に変換して
 * navigator.credentials.create を実行し、サーバー送信用 JSON を返す。
 */
export async function startPasskeyRegistration(
  options: RegisterOptions
): Promise<Record<string, unknown>> {
  const publicKey: PublicKeyCredentialCreationOptions = {
    challenge: base64urlToBuffer(options.challenge),
    timeout: options.timeout,
    rp: options.rp || { name: 'PhotoNest' },
    user: {
      id: base64urlToBuffer(options.user.id),
      name: options.user.name,
      displayName: options.user.displayName,
    },
    pubKeyCredParams: options.pubKeyCredParams,
    attestation: options.attestation,
    excludeCredentials: (options.excludeCredentials || []).map((c) => ({
      id: base64urlToBuffer(c.id),
      type: c.type,
    })),
    authenticatorSelection: options.authenticatorSelection,
  };

  const credential = (await navigator.credentials.create({
    publicKey,
  })) as PublicKeyCredential | null;

  if (!credential) {
    throw new Error('passkey_canceled');
  }

  const response = credential.response as AuthenticatorAttestationResponse;
  const result: Record<string, unknown> = {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
    },
  };

  if (typeof response.getTransports === 'function') {
    (result.response as Record<string, unknown>).transports = response.getTransports();
  }

  return result;
}

interface AuthOptions {
  challenge: string;
  timeout?: number;
  rpId?: string;
  userVerification?: UserVerificationRequirement;
  allowCredentials?: Array<{
    id: string;
    type: 'public-key';
    transports?: AuthenticatorTransport[];
  }>;
}

/**
 * サーバーが返した認証オプション(base64url)を WebAuthn 用に変換して
 * navigator.credentials.get を実行し、サーバー送信用 JSON を返す。
 */
export async function startPasskeyAuthentication(
  options: AuthOptions
): Promise<Record<string, unknown>> {
  const publicKey: PublicKeyCredentialRequestOptions = {
    challenge: base64urlToBuffer(options.challenge),
    timeout: options.timeout,
    rpId: options.rpId,
    userVerification: options.userVerification,
    allowCredentials: (options.allowCredentials || []).map((c) => ({
      id: base64urlToBuffer(c.id),
      type: c.type,
      transports: c.transports,
    })),
  };

  const credential = (await navigator.credentials.get({
    publicKey,
  })) as PublicKeyCredential | null;

  if (!credential) {
    throw new Error('passkey_canceled');
  }

  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle
        ? bufferToBase64url(response.userHandle)
        : null,
    },
  };
}
