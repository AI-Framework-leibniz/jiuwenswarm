import { configureDesignCanvasHost, designCanvasLocales } from '@designswarm/canvas';
import ChatModelSelector from '../components/ChatPanel/ChatModelSelector';
import { InlineQuestionCard } from '../components/ChatPanel/InlineQuestionCard';
import { MessageList } from '../components/ChatPanel/MessageList';
import { InteractionSlot } from '../components/InteractionSlot';
import { MarkdownRenderer } from '../components/MarkdownRenderer';
import { ModelProviderIcon } from '../components/ModelProviderIcon';
import { downloadPreviewFile } from '../components/ui/FilePreviewPanel/filePreviewShared';
import i18n from '../i18n';
import { webClient } from '../services/webClient';
import { useChatStore } from '../stores/chatStore';
import { resolveChatModelSelection, useSessionStore } from '../stores/sessionStore';
import { useWorkspaceStore } from '../stores/workspaceStore';

configureDesignCanvasHost({
  webClient,
  useChatStore,
  useSessionStore,
  useWorkspaceStore,
  resolveChatModelSelection,
  components: {
    MarkdownRenderer,
    ModelProviderIcon,
    MessageList,
    InlineQuestionCard,
    InteractionSlot,
    ChatModelSelector,
  },
  downloadPreviewFile,
});

// The canvas ships the `designer.*` strings; keys defined by jiuwenswarm win.
for (const [lng, bundle] of Object.entries(designCanvasLocales)) {
  i18n.addResourceBundle(lng, 'translation', bundle, true, false);
}
