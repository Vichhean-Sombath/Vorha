export type LocalMediaType = "audio" | "video";

type LocalMediaRecord = {
  key: string;
  ownerKey: string;
  soundId: number;
  fileName: string;
  mediaType?: LocalMediaType;
  blob: Blob;
};

const DATABASE = "vorha-local-audio";
const STORE = "tracks";

function getOwnerKey(userId: number | null) {
  return userId === null ? "guest" : `user:${userId}`;
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("Local audio storage is not available in this browser."));
      return;
    }
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE)) database.createObjectStore(STORE, { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open local audio storage."));
  });
}

export function getLocalMediaType(file: Pick<File, "name" | "type">): LocalMediaType | null {
  if (file.type.startsWith("audio/") || /\.(mp3|m4a|aac|wav|ogg|oga|opus|flac|weba)$/i.test(file.name)) return "audio";
  if (file.type.startsWith("video/") || /\.(mp4|m4v|mov|webm|mkv|3gp)$/i.test(file.name)) return "video";
  return null;
}

export async function saveLocalMedia(userId: number | null, soundId: number, file: File, mediaType: LocalMediaType) {
  const database = await openDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE, "readwrite");
      const record: LocalMediaRecord = {
        key: `${getOwnerKey(userId)}:${soundId}`,
        ownerKey: getOwnerKey(userId),
        soundId,
        fileName: file.name,
        mediaType,
        blob: file,
      };
      transaction.objectStore(STORE).put(record);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Could not save the media file."));
      transaction.onabort = () => reject(transaction.error ?? new Error("Could not save the media file."));
    });
  } finally {
    database.close();
  }
}

export async function createLocalMediaUrl(userId: number | null, soundId: number): Promise<{ url: string; mediaType: LocalMediaType } | null> {
  const database = await openDatabase();
  try {
    const record = await new Promise<LocalMediaRecord | undefined>((resolve, reject) => {
      const request = database.transaction(STORE, "readonly").objectStore(STORE).get(`${getOwnerKey(userId)}:${soundId}`);
      request.onsuccess = () => resolve(request.result as LocalMediaRecord | undefined);
      request.onerror = () => reject(request.error ?? new Error("Could not read the saved media file."));
    });
    return record?.blob ? { url: URL.createObjectURL(record.blob), mediaType: record.mediaType ?? "audio" } : null;
  } finally {
    database.close();
  }
}

export async function listLocalAudioSoundIds(userId: number | null): Promise<number[]> {
  const database = await openDatabase();
  try {
    return await new Promise<number[]>((resolve, reject) => {
      const request = database.transaction(STORE, "readonly").objectStore(STORE).getAll();
      request.onsuccess = () => {
        const owner = getOwnerKey(userId);
        resolve((request.result as LocalMediaRecord[]).filter((record) => record.ownerKey === owner).map((record) => record.soundId));
      };
      request.onerror = () => reject(request.error ?? new Error("Could not read local audio storage."));
    });
  } finally {
    database.close();
  }
}

export async function removeLocalMedia(userId: number | null, soundId: number) {
  const database = await openDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE, "readwrite");
      transaction.objectStore(STORE).delete(`${getOwnerKey(userId)}:${soundId}`);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Could not remove the saved audio file."));
      transaction.onabort = () => reject(transaction.error ?? new Error("Could not remove the saved audio file."));
    });
  } finally {
    database.close();
  }
}
