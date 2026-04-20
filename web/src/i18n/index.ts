/**
 * react-i18next 脚手架（Phase 1 预留；管理后台 admin 此期仍为中文 only）。
 *
 * 未来 Phase 3 的"翻译审校"模块会消费这里的 t()/useTranslation。现在提供
 * 极简的 zh-CN/en-US 双空 namespace 结构让代码能 import。
 *
 * Convention（lobehub skill 规范）：flat keys with dot notation，不用
 * 嵌套对象；参数 `{{var}}`。
 */
import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';

import enUS from './locales/en-US.json';
import zhCN from './locales/zh-CN.json';

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      'zh-CN': zhCN,
      'en-US': enUS,
    },
    fallbackLng: 'zh-CN',
    defaultNS: 'common',
    ns: ['common'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['cookie', 'navigator'],
      lookupCookie: 'NEXT_LOCALE',
      caches: ['cookie'],
    },
  });

export default i18n;
