import { describe, it, expect, beforeEach } from 'vitest';
import { DerivedStateStore } from '../src/state/derived-state';

describe('DerivedStateStore (bot-aware)', () => {
  let store: DerivedStateStore;

  const BOT_A = 'bot-alpha';
  const BOT_B = 'bot-beta';

  beforeEach(() => {
    store = new DerivedStateStore();
  });

  // ========== Mirrors ==========
  describe('mirrors', () => {
    it('should add and retrieve mirror scoped by botId', () => {
      store.addMirror(BOT_A, 100, 200);
      expect(store.getMirrors(BOT_A, 100)).toEqual([
        { botId: BOT_A, sourceChatId: 100, targetChatId: 200 },
      ]);
    });

    it('should remove mirror scoped by botId', () => {
      store.addMirror(BOT_A, 100, 200);
      expect(store.removeMirror(BOT_A, 100, 200)).toBe(true);
      expect(store.getMirrors(BOT_A, 100)).toEqual([]);
    });

    it('should return empty array for unknown source', () => {
      expect(store.getMirrors(BOT_A, 999)).toEqual([]);
    });

    it('should isolate mirrors between bots in the same chat', () => {
      store.addMirror(BOT_A, 100, 200);
      store.addMirror(BOT_B, 100, 300);

      // bot-alpha only sees its own mirror
      expect(store.getMirrors(BOT_A, 100)).toEqual([
        { botId: BOT_A, sourceChatId: 100, targetChatId: 200 },
      ]);
      // bot-beta only sees its own mirror
      expect(store.getMirrors(BOT_B, 100)).toEqual([
        { botId: BOT_B, sourceChatId: 100, targetChatId: 300 },
      ]);
    });

    it('should allow same source→target pair for different bots', () => {
      store.addMirror(BOT_A, 100, 200);
      store.addMirror(BOT_B, 100, 200);
      expect(store.getMirrors(BOT_A, 100)).toHaveLength(1);
      expect(store.getMirrors(BOT_B, 100)).toHaveLength(1);
    });

    it('listMirrorsByBot returns all mirrors for one bot', () => {
      store.addMirror(BOT_A, 1, 2);
      store.addMirror(BOT_A, 3, 4);
      store.addMirror(BOT_B, 5, 6);
      expect(store.listMirrorsByBot(BOT_A)).toHaveLength(2);
      expect(store.listMirrorsByBot(BOT_B)).toHaveLength(1);
    });
  });

  // ========== Channel Directory ==========
  describe('channel directory', () => {
    it('should register and lookup channel scoped by botId', () => {
      store.registerChannel(BOT_A, 'announcements', -1001234);
      expect(store.lookupChannel(BOT_A, 'announcements')).toEqual({
        botId: BOT_A,
        name: 'announcements',
        chatId: -1001234,
      });
    });

    it('should remove channel scoped by botId', () => {
      store.registerChannel(BOT_A, 'announcements', -1001234);
      expect(store.removeChannel(BOT_A, 'announcements')).toBe(true);
      expect(store.lookupChannel(BOT_A, 'announcements')).toBeUndefined();
    });

    it('should return undefined for unknown channel', () => {
      expect(store.lookupChannel(BOT_A, 'nope')).toBeUndefined();
    });

    it('should isolate channel directory between bots', () => {
      store.registerChannel(BOT_A, 'news', -100);
      store.registerChannel(BOT_B, 'news', -200);

      expect(store.lookupChannel(BOT_A, 'news')?.chatId).toBe(-100);
      expect(store.lookupChannel(BOT_B, 'news')?.chatId).toBe(-200);
    });

    it('removing one bot channel does not affect another bot', () => {
      store.registerChannel(BOT_A, 'ch', -100);
      store.registerChannel(BOT_B, 'ch', -200);
      store.removeChannel(BOT_A, 'ch');
      expect(store.lookupChannel(BOT_A, 'ch')).toBeUndefined();
      expect(store.lookupChannel(BOT_B, 'ch')?.chatId).toBe(-200);
    });

    it('listChannelsByBot returns only that bot entries', () => {
      store.registerChannel(BOT_A, 'a', -1);
      store.registerChannel(BOT_A, 'b', -2);
      store.registerChannel(BOT_B, 'c', -3);
      expect(store.listChannelsByBot(BOT_A)).toHaveLength(2);
      expect(store.listChannelsByBot(BOT_B)).toHaveLength(1);
    });
  });

  // ========== Topic Bindings ==========
  describe('topic bindings', () => {
    it('should bind and lookup topic scoped by botId', () => {
      store.bindTopic(BOT_A, -1001234, 'general', 42);
      expect(store.lookupTopic(BOT_A, -1001234, 'general')).toEqual({
        botId: BOT_A,
        chatId: -1001234,
        topicName: 'general',
        threadId: 42,
      });
    });

    it('should unbind topic scoped by botId', () => {
      store.bindTopic(BOT_A, -1001234, 'general', 42);
      expect(store.unbindTopic(BOT_A, -1001234, 'general')).toBe(true);
      expect(store.lookupTopic(BOT_A, -1001234, 'general')).toBeUndefined();
    });

    it('should return undefined for unknown topic', () => {
      expect(store.lookupTopic(BOT_A, -1001234, 'unknown')).toBeUndefined();
    });

    it('should isolate topic bindings between bots in the same chat', () => {
      store.bindTopic(BOT_A, -1001234, 'general', 42);
      store.bindTopic(BOT_B, -1001234, 'general', 99);

      expect(store.lookupTopic(BOT_A, -1001234, 'general')?.threadId).toBe(42);
      expect(store.lookupTopic(BOT_B, -1001234, 'general')?.threadId).toBe(99);
    });

    it('unbinding for one bot does not affect another', () => {
      store.bindTopic(BOT_A, -1001234, 'general', 42);
      store.bindTopic(BOT_B, -1001234, 'general', 99);
      store.unbindTopic(BOT_A, -1001234, 'general');
      expect(store.lookupTopic(BOT_A, -1001234, 'general')).toBeUndefined();
      expect(store.lookupTopic(BOT_B, -1001234, 'general')?.threadId).toBe(99);
    });

    it('listTopicsByBot returns only that bot bindings', () => {
      store.bindTopic(BOT_A, -100, 'a', 1);
      store.bindTopic(BOT_A, -100, 'b', 2);
      store.bindTopic(BOT_B, -100, 'c', 3);
      expect(store.listTopicsByBot(BOT_A)).toHaveLength(2);
      expect(store.listTopicsByBot(BOT_B)).toHaveLength(1);
    });
  });

  // ========== Utility ==========
  describe('clear / clearBot', () => {
    it('clear() removes all state for all bots', () => {
      store.addMirror(BOT_A, 1, 2);
      store.addMirror(BOT_B, 3, 4);
      store.registerChannel(BOT_A, 'ch', -100);
      store.bindTopic(BOT_B, -100, 'tp', 7);
      store.clear();
      expect(store.getMirrors(BOT_A, 1)).toEqual([]);
      expect(store.getMirrors(BOT_B, 3)).toEqual([]);
      expect(store.lookupChannel(BOT_A, 'ch')).toBeUndefined();
      expect(store.lookupTopic(BOT_B, -100, 'tp')).toBeUndefined();
    });

    it('clearBot() removes only the target bot state', () => {
      store.addMirror(BOT_A, 1, 2);
      store.addMirror(BOT_B, 3, 4);
      store.registerChannel(BOT_A, 'ch', -100);
      store.registerChannel(BOT_B, 'ch', -200);
      store.bindTopic(BOT_A, -100, 'tp', 7);
      store.bindTopic(BOT_B, -100, 'tp', 8);

      store.clearBot(BOT_A);

      // BOT_A wiped
      expect(store.getMirrors(BOT_A, 1)).toEqual([]);
      expect(store.lookupChannel(BOT_A, 'ch')).toBeUndefined();
      expect(store.lookupTopic(BOT_A, -100, 'tp')).toBeUndefined();
      expect(store.listMirrorsByBot(BOT_A)).toEqual([]);

      // BOT_B untouched
      expect(store.getMirrors(BOT_B, 3)).toHaveLength(1);
      expect(store.lookupChannel(BOT_B, 'ch')?.chatId).toBe(-200);
      expect(store.lookupTopic(BOT_B, -100, 'tp')?.threadId).toBe(8);
    });
  });
});
