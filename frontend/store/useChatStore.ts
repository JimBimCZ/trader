"use client";

/** Conversation state for the assistant panel. */

import { create } from "zustand";
import { fetchChatHistory, sendChatMessage } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { ChatMessage } from "@/lib/types";

interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  refresh: () => Promise<void>;
  send: (text: string) => Promise<void>;
}

let localId = 0;
const nextLocalId = () => `local-${++localId}`;

export const useChatStore = create<ChatState>()((set, get) => ({
  messages: [],
  isLoading: false,

  refresh: async () => {
    set({ messages: await fetchChatHistory() });
  },

  send: async (text) => {
    // Show the user's own message at once; the assistant's reply follows.
    const pending: ChatMessage = {
      id: nextLocalId(),
      role: "user",
      content: text,
      actions: null,
      createdAt: new Date().toISOString(),
    };
    set({ messages: [...get().messages, pending], isLoading: true });

    try {
      const reply = await sendChatMessage(text);
      set({
        messages: [
          ...get().messages,
          {
            id: nextLocalId(),
            role: "assistant",
            content: reply.message,
            actions: reply.actions,
            createdAt: new Date().toISOString(),
          },
        ],
      });
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "The assistant could not be reached.";
      set({
        messages: [
          ...get().messages,
          {
            id: nextLocalId(),
            role: "assistant",
            content: message,
            actions: [],
            createdAt: new Date().toISOString(),
          },
        ],
      });
    } finally {
      set({ isLoading: false });
    }
  },
}));
