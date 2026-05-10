// src/state/derived-state.ts
//
// Derived state: mirror mappings, channel directory, topic bindings
// These are secondary indexes / caches that the bot maintains at runtime.
//
// All state is scoped by botId so multiple bots sharing a chat don't collide.

/**
 * Mirror mapping: links two chats so messages are forwarded between them.
 * Scoped per bot.
 */
export interface MirrorMapping {
  botId: string;
  sourceChatId: number;
  targetChatId: number;
}

/**
 * Channel directory: maps a channel/group name to its chat ID for quick lookup.
 * Scoped per bot.
 */
export interface ChannelDirectoryEntry {
  botId: string;
  name: string;
  chatId: number;
}

/**
 * Topic binding: in supergroups with topics enabled, maps a topic name to its thread ID.
 * Scoped per bot.
 */
export interface TopicBinding {
  botId: string;
  chatId: number;
  topicName: string;
  threadId: number;
}

export class DerivedStateStore {
  private mirrors: Map<string, MirrorMapping> = new Map();
  private channelDirectory: Map<string, ChannelDirectoryEntry> = new Map();
  private topicBindings: Map<string, TopicBinding> = new Map();

  // ---- key helpers (bot-scoped) ----
  private mirrorKey(botId: string, sourceChatId: number, targetChatId: number): string {
    return `${botId}:${sourceChatId}:${targetChatId}`;
  }

  private channelKey(botId: string, name: string): string {
    return `${botId}:${name}`;
  }

  private topicKey(botId: string, chatId: number, topicName: string): string {
    return `${botId}:${chatId}:${topicName}`;
  }

  // --- Mirror ---
  addMirror(botId: string, sourceChatId: number, targetChatId: number): void {
    const key = this.mirrorKey(botId, sourceChatId, targetChatId);
    this.mirrors.set(key, { botId, sourceChatId, targetChatId });
  }

  removeMirror(botId: string, sourceChatId: number, targetChatId: number): boolean {
    return this.mirrors.delete(this.mirrorKey(botId, sourceChatId, targetChatId));
  }

  getMirrors(botId: string, sourceChatId: number): MirrorMapping[] {
    return [...this.mirrors.values()].filter(
      m => m.botId === botId && m.sourceChatId === sourceChatId,
    );
  }

  listMirrorsByBot(botId: string): MirrorMapping[] {
    return [...this.mirrors.values()].filter(m => m.botId === botId);
  }

  // --- Channel directory ---
  registerChannel(botId: string, name: string, chatId: number): void {
    const key = this.channelKey(botId, name);
    this.channelDirectory.set(key, { botId, name, chatId });
  }

  lookupChannel(botId: string, name: string): ChannelDirectoryEntry | undefined {
    return this.channelDirectory.get(this.channelKey(botId, name));
  }

  removeChannel(botId: string, name: string): boolean {
    return this.channelDirectory.delete(this.channelKey(botId, name));
  }

  listChannelsByBot(botId: string): ChannelDirectoryEntry[] {
    return [...this.channelDirectory.values()].filter(e => e.botId === botId);
  }

  // --- Topic bindings ---
  bindTopic(botId: string, chatId: number, topicName: string, threadId: number): void {
    const key = this.topicKey(botId, chatId, topicName);
    this.topicBindings.set(key, { botId, chatId, topicName, threadId });
  }

  lookupTopic(botId: string, chatId: number, topicName: string): TopicBinding | undefined {
    return this.topicBindings.get(this.topicKey(botId, chatId, topicName));
  }

  unbindTopic(botId: string, chatId: number, topicName: string): boolean {
    return this.topicBindings.delete(this.topicKey(botId, chatId, topicName));
  }

  listTopicsByBot(botId: string): TopicBinding[] {
    return [...this.topicBindings.values()].filter(t => t.botId === botId);
  }

  // --- Utility ---

  /** Clear ALL derived state (all bots). */
  clear(): void {
    this.mirrors.clear();
    this.channelDirectory.clear();
    this.topicBindings.clear();
  }

  /** Clear derived state for a single bot, leaving other bots untouched. */
  clearBot(botId: string): void {
    for (const [k, v] of this.mirrors) {
      if (v.botId === botId) this.mirrors.delete(k);
    }
    for (const [k, v] of this.channelDirectory) {
      if (v.botId === botId) this.channelDirectory.delete(k);
    }
    for (const [k, v] of this.topicBindings) {
      if (v.botId === botId) this.topicBindings.delete(k);
    }
  }
}
