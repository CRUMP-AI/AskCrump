import { Capacitor } from '@capacitor/core';
import { App } from '@capacitor/app';
import { Haptics, ImpactStyle, NotificationType } from '@capacitor/haptics';
import { Keyboard } from '@capacitor/keyboard';
import { Network } from '@capacitor/network';
import { PushNotifications } from '@capacitor/push-notifications';
import { StatusBar, Style } from '@capacitor/status-bar';
import { SecureStorage } from '@aparajita/capacitor-secure-storage';
import { Media } from '@capacitor-community/media';
import { Purchases, LOG_LEVEL } from '@revenuecat/purchases-capacitor';

window.CrumpNative = {
  Capacitor,
  App,
  Haptics,
  ImpactStyle,
  NotificationType,
  Keyboard,
  Network,
  PushNotifications,
  StatusBar,
  Style,
  SecureStorage,
  Media,
  Purchases,
  LOG_LEVEL,
  isNative: Capacitor.isNativePlatform(),
};

async function configureNativeExperience() {
  if (!Capacitor.isNativePlatform()) return;
  document.documentElement.classList.add('native-app');
  await Promise.allSettled([
    StatusBar.setStyle({ style: Style.Light }),
    Keyboard.setAccessoryBarVisible({ isVisible: true }),
  ]);

  await PushNotifications.addListener('registration', token => {
    window.dispatchEvent(new CustomEvent('crump:push-registration', { detail: token }));
  });
  await PushNotifications.addListener('registrationError', error => {
    window.dispatchEvent(new CustomEvent('crump:push-registration-error', { detail: error }));
  });
  await PushNotifications.addListener('pushNotificationReceived', notification => {
    window.dispatchEvent(new CustomEvent('crump:push-received', { detail: notification }));
  });
  await PushNotifications.addListener('pushNotificationActionPerformed', action => {
    window.dispatchEvent(new CustomEvent('crump:push-action', { detail: action }));
  });

  if (Capacitor.getPlatform() === 'android') {
    await PushNotifications.createChannel({
      id: 'crump_check_ins',
      name: 'Crump Check-ins',
      description: 'Meaningful follow-ups from Ask Crump',
      importance: 4,
      visibility: 1,
      vibration: true,
    }).catch(() => {});
  }

  const initialNetwork = await Network.getStatus().catch(() => ({ connected: navigator.onLine }));
  window.dispatchEvent(new CustomEvent('crump:network-status', { detail: initialNetwork }));
  await Network.addListener('networkStatusChange', status => {
    window.dispatchEvent(new CustomEvent('crump:network-status', { detail: status }));
  });

  await Keyboard.addListener('keyboardWillShow', info => {
    document.documentElement.style.setProperty('--native-keyboard-height', `${Number(info.keyboardHeight || 0)}px`);
    document.documentElement.classList.add('keyboard-visible');
  });
  await Keyboard.addListener('keyboardWillHide', () => {
    document.documentElement.style.setProperty('--native-keyboard-height', '0px');
    document.documentElement.classList.remove('keyboard-visible');
  });
}

configureNativeExperience().finally(() => {
  window.dispatchEvent(new CustomEvent('crump:native-ready', { detail: window.CrumpNative }));
});
