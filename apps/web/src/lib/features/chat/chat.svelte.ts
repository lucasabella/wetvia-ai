/** Lege gespreksstaat. De chat zelf komt in een later issue. */
export class ChatStore {
  messages = $state<string[]>([]);
}
