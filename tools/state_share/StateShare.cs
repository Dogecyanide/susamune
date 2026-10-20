using System;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace MoonshineStateShare
{
    public sealed class Archive
    {
        public string Name { get; internal set; }
        public string Region { get; internal set; }
        public string Build { get; internal set; }
        public string SetupId { get; internal set; }
        public string Scene { get; internal set; }
        public uint Snapshot { get; internal set; }
        public uint PackedBytes { get; internal set; }
        public uint RawBytes { get; internal set; }
        public bool KnownBuildContract { get; internal set; }
        internal byte[] Bytes;
    }

    public static class Files
    {
        private const int HeaderSize = 96;
        private const uint SnapshotVersion = 18;
        private const int MaxMetadata = 7168;
        private const int MaxPayload = 0x02000000;
        private const int MaxArchive = HeaderSize + MaxMetadata + MaxPayload;
        private static readonly uint[] CrcTable = MakeCrcTable();

        private static uint[] MakeCrcTable()
        {
            uint[] table = new uint[256];
            for (uint i = 0; i < 256; ++i)
            {
                uint c = i;
                for (int n = 0; n < 8; ++n) c = (c >> 1) ^ ((c & 1) != 0 ? 0xEDB88320u : 0u);
                table[i] = c;
            }
            return table;
        }

        private static uint U32(byte[] bytes, int at)
        {
            return ((uint)bytes[at] << 24) | ((uint)bytes[at + 1] << 16) |
                ((uint)bytes[at + 2] << 8) | bytes[at + 3];
        }

        private static uint Crc(byte[] bytes, int at, int count, bool header)
        {
            uint c = 0xFFFFFFFFu;
            for (int i = at; i < at + count; ++i)
            {
                byte value = header && i >= 48 && i < 52 ? (byte)0 : bytes[i];
                c = CrcTable[(c ^ value) & 255] ^ (c >> 8);
            }
            return ~c;
        }

        private static uint Fingerprint(byte[] bytes, int at, int count, int skip)
        {
            uint hash = 2166136261u;
            for (int i = 0; i < count; ++i)
                hash = unchecked((hash ^ ((i >= skip && i < skip + 4) ? 0u : bytes[at + i])) * 16777619u);
            return hash;
        }

        private static bool Mem1(uint address, uint size)
        {
            return size != 0 && address >= 0x80000000u && (ulong)address + size <= 0x81800000u;
        }

        private static bool OwnerAddress(uint address)
        {
            if ((address & 3) != 0) return false;
            return Mem1(address, 4) ||
                (address >= 0x70000000u && (ulong)address + 4 <= 0x72000000u) ||
                (address >= 0x90000000u && (ulong)address + 4 <= 0x94000000u);
        }

        private static void ValidateMetadata(byte[] bytes, uint game, uint build, uint setup,
                                             uint scene, uint metadata, uint raw, uint packed)
        {
            // StoredState's PPC ABI differs by the two extra JP audio carve-out regions.
            int regionCapacity = game == 0x474D534A ? 20 : 18;
            int size = game == 0x474D534A ? 6960 : 6936;
            int profile = HeaderSize + (game == 0x474D534A ? 1016 : 992);
            int tail = HeaderSize + size - 24;
            uint version = game == 0x474D534A ? 1u : game == 0x474D5345 ? 2u : 3u;
            if (metadata != size)
                throw new InvalidDataException("This state's metadata does not match the current region's snapshot-18 layout.");
            int m = HeaderSize;
            if (U32(bytes, m) != 0x53555341 || U32(bytes, m + 4) != SnapshotVersion ||
                U32(bytes, m + 8) != version || bytes[m + 20] != (scene >> 24) ||
                bytes[m + 21] != ((scene >> 16) & 255) || U32(bytes, tail + 16) != (scene & 65535) ||
                U32(bytes, tail) == 0 || U32(bytes, tail + 4) != raw || U32(bytes, tail + 8) != packed ||
                Fingerprint(bytes, m, size - 4, -4) != U32(bytes, tail + 20))
                throw new InvalidDataException("The state's internal identity or metadata fingerprint is invalid.");
            uint heap = U32(bytes, m + 12), heapSize = U32(bytes, m + 16), regions = U32(bytes, m + 24);
            if (!Mem1(heap, heapSize) || regions == 0 || regions > regionCapacity)
                throw new InvalidDataException("The state's memory layout is invalid.");
            ulong offset = 0;
            for (uint i = 0; i < regions; ++i)
            {
                int entry = m + 40 + (int)i * 12;
                uint address = U32(bytes, entry), length = U32(bytes, entry + 4);
                if (!Mem1(address, length) || U32(bytes, entry + 8) != offset ||
                    offset + length > raw || (i + 1 == regions && (address != heap || length != heapSize)))
                    throw new InvalidDataException("The state's saved memory regions are invalid.");
                offset += length;
            }
            uint anchors = U32(bytes, profile + 20), keeps = U32(bytes, profile + 24);
            if (U32(bytes, profile) != 0x534F574E || U32(bytes, profile + 4) != 1 ||
                U32(bytes, profile + 8) != version || U32(bytes, profile + 12) != build ||
                U32(bytes, profile + 16) != setup || anchors == 0 || anchors > 640 || keeps == 0 || keeps > 96 ||
                Fingerprint(bytes, profile, 5920, 28) != U32(bytes, profile + 28))
                throw new InvalidDataException("The state's resource ownership metadata is invalid.");
            for (uint i = 0; i < anchors; ++i)
                if (!OwnerAddress(U32(bytes, profile + 32 + (int)i * 8)))
                    throw new InvalidDataException("The state contains an invalid resource owner address.");
            ulong end = 0;
            for (uint i = 0; i < keeps; ++i)
            {
                int entry = profile + 5152 + (int)i * 8;
                uint address = U32(bytes, entry), length = U32(bytes, entry + 4);
                if (!Mem1(address, length) || address <= end)
                    throw new InvalidDataException("The state's preserved resource ranges are invalid.");
                end = (ulong)address + length;
            }
        }

        private static byte[] ReadBounded(Stream input, long length)
        {
            if (length < HeaderSize || length > MaxArchive)
                throw new InvalidDataException("The state file has an unsupported size.");
            byte[] bytes = new byte[(int)length];
            int at = 0;
            while (at < bytes.Length)
            {
                int read = input.Read(bytes, at, bytes.Length - at);
                if (read == 0) throw new InvalidDataException("The state file is incomplete.");
                at += read;
            }
            if (input.ReadByte() != -1) throw new InvalidDataException("The state file contains unexpected extra data.");
            return bytes;
        }

        public static Archive Read(string path)
        {
            byte[] bytes;
            using (FileStream file = new FileStream(Path.GetFullPath(path), FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (String.Equals(Path.GetExtension(path), ".zip", StringComparison.OrdinalIgnoreCase))
                {
                    if (file.Length > MaxArchive + 2097152)
                        throw new InvalidDataException("This ZIP is too large for one shared state.");
                    using (ZipArchive zip = new ZipArchive(file, ZipArchiveMode.Read, true))
                    {
                        ZipArchiveEntry state = null;
                        if (zip.Entries.Count > 2) throw new InvalidDataException("Use a ZIP created by Share a state, or choose the .mss file directly.");
                        foreach (ZipArchiveEntry entry in zip.Entries)
                        {
                            if (entry.FullName == "state.mss" && state == null) state = entry;
                            else if (entry.FullName != "README.txt" || entry.Length > 16384)
                                throw new InvalidDataException("This ZIP is not a supported Moonshine state package.");
                        }
                        if (state == null) throw new InvalidDataException("The ZIP does not contain state.mss.");
                        using (Stream input = state.Open()) bytes = ReadBounded(input, state.Length);
                    }
                }
                else
                {
                    if (!String.Equals(Path.GetExtension(path), ".mss", StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Choose a Moonshine .mss state or a shared-state ZIP.");
                    bytes = ReadBounded(file, file.Length);
                }
            }
            return Validate(bytes);
        }

        private static Archive Validate(byte[] bytes)
        {
            uint metadata = U32(bytes, 12), packed = U32(bytes, 16), raw = U32(bytes, 20);
            uint game = U32(bytes, 24), build = U32(bytes, 28), snapshot = U32(bytes, 32), setup = U32(bytes, 36);
            if (U32(bytes, 0) != 0x4D535341 || U32(bytes, 4) != 1 || U32(bytes, 8) != HeaderSize ||
                metadata == 0 || metadata > MaxMetadata || packed == 0 || packed > MaxPayload ||
                raw == 0 || raw > MaxPayload || (long)HeaderSize + metadata + packed != bytes.Length ||
                U32(bytes, 56) != 0 || U32(bytes, 60) != 0)
                throw new InvalidDataException("The state header or file length is invalid.");
            if (game != 0x474D534A && game != 0x474D5345 && game != 0x474D5350)
                throw new InvalidDataException("The state has an unknown game region.");
            if (snapshot != SnapshotVersion || build == 0 || setup == 0)
                throw new InvalidDataException("This helper supports snapshot-18 savestates. Use the matching Moonshine build for other files.");
            if (Crc(bytes, 0, HeaderSize, true) != U32(bytes, 48) ||
                Crc(bytes, HeaderSize, (int)metadata, false) != U32(bytes, 40) ||
                Crc(bytes, HeaderSize + (int)metadata, (int)packed, false) != U32(bytes, 44))
                throw new InvalidDataException("The state failed its integrity checks. Ask for a new copy.");
            int length = 0;
            while (length < 32 && bytes[64 + length] != 0)
            {
                if (bytes[64 + length] < 32 || bytes[64 + length] > 126)
                    throw new InvalidDataException("The state name is damaged.");
                ++length;
            }
            if (length == 32) throw new InvalidDataException("The state name is incomplete.");
            uint scene = U32(bytes, 52);
            if ((scene >> 24) > 0x3c || ((scene >> 16) & 255) > 9 || (scene & 65535) > 255)
                throw new InvalidDataException("The state has an unsupported gameplay scene.");
            ValidateMetadata(bytes, game, build, setup, scene, metadata, raw, packed);
            bool known = build == 0x4D530011 ||
                (game == 0x474D534A && (build == 0x7D55E8F2 || build == 0x8C8B60C4)) ||
                (game == 0x474D5345 && (build == 0x46F87973 || build == 0xD784A910)) ||
                (game == 0x474D5350 && (build == 0xEA3C3DFD || build == 0x96DD313A));
            return new Archive {
                Name = Encoding.ASCII.GetString(bytes, 64, length),
                Region = game == 0x474D534A ? "JP" : game == 0x474D5345 ? "US" : "PAL",
                Build = build.ToString("X8"), SetupId = setup.ToString("X8"),
                Scene = String.Format("Area {0}, episode index {1}, parent index {2} ({3:X8})",
                    scene >> 24, (scene >> 16) & 255, scene & 65535, scene),
                Snapshot = snapshot, PackedBytes = packed, RawBytes = raw,
                KnownBuildContract = known, Bytes = bytes
            };
        }

        private static string Instructions(Archive state, string setupNote)
        {
            if (setupNote == null) setupNote = "";
            if (setupNote.Length > 4000) throw new ArgumentException("Keep the setup note below 4,000 characters.");
            return "MOONSHINE SHARED SAVESTATE\r\n\r\n" +
                "Name: " + state.Name + "\r\nRegion: " + state.Region +
                "\r\nBuild/restore contract: " + state.Build + "\r\nSnapshot: " + state.Snapshot +
                "\r\nLauncher setup ID: " + state.SetupId + "\r\nScene: " + state.Scene +
                "\r\n\r\nSender's setup notes:\r\n" + (setupNote.Length == 0 ? "Not supplied." : setupNote) +
                "\r\n\r\nOpen Import a state.cmd and choose this ZIP, then your Wii SD card.\r\n" +
                "Boot the matching game region and compatible Moonshine build with the same launcher setup.\r\n" +
                "Enter the same stage and episode. Refresh the SD states list, choose this state with Y,\r\n" +
                "then use your normal Load bind. This direct load leaves your three RAM slots alone.\r\n" +
                "A imports into the selected Save to RAM slot; use that only when you want to replace it.\r\n\r\n" +
                "Integrity checking does not prove that another Wii can restore this state. The game\r\n" +
                "still checks build compatibility, region, launcher configuration, scene, heap and\r\n" +
                "resource ownership. Different setups may be refused. There is no PAL/JP conversion,\r\n" +
                "state relocation or compatibility bypass. Keep the sender's original file.\r\n" +
                "This package contains the state as first named; later SD rename sidecars are not included.\r\n";
        }

        public static string Export(string source, string destination, string setupNote)
        {
            Archive state = Read(source);
            string note = Instructions(state, setupNote);
            string path = Path.GetFullPath(destination);
            if (!String.Equals(Path.GetExtension(path), ".zip", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Choose a .zip destination.");
            bool created = false;
            try
            {
                using (FileStream output = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None))
                {
                    created = true;
                    using (ZipArchive zip = new ZipArchive(output, ZipArchiveMode.Create, true))
                    {
                        using (Stream entry = zip.CreateEntry("state.mss", CompressionLevel.NoCompression).Open())
                            entry.Write(state.Bytes, 0, state.Bytes.Length);
                        using (StreamWriter writer = new StreamWriter(zip.CreateEntry("README.txt").Open(), new UTF8Encoding(false)))
                            writer.Write(note);
                    }
                    output.Flush(true);
                }
                return path;
            }
            catch
            {
                if (created) File.Delete(path);
                throw;
            }
        }

        public static string Import(string source, string sdRoot)
        {
            Archive state = Read(source);
            if (!state.KnownBuildContract)
                throw new InvalidDataException("This helper does not recognize this state's build contract. Use the helper supplied with its Moonshine build.");
            string root = Path.GetFullPath(sdRoot);
            if (!Directory.Exists(root)) throw new DirectoryNotFoundException("Choose the SD card's existing root folder.");
            string directory = Path.Combine(root, "Moonshine data", "states");
            Directory.CreateDirectory(directory);
            for (uint id = 1; id <= 99999999; ++id)
            {
                string stem = "state_" + id.ToString("D8");
                if (Directory.GetFileSystemEntries(directory, stem + ".*").Length != 0) continue;
                string marker = Path.Combine(directory, stem + ".used");
                try { using (FileStream reserved = new FileStream(marker, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { reserved.Flush(true); } }
                catch (IOException) { if (File.Exists(marker)) continue; throw; }
                // The persistent reservation prevents another helper from reusing this ID.
                string temporary = Path.Combine(directory, stem + ".tmp");
                string destination = Path.Combine(directory, stem + ".mss");
                bool created = false;
                try
                {
                    if (Directory.GetFileSystemEntries(directory, stem + ".*").Length != 1) continue;
                    using (FileStream output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    {
                        created = true;
                        output.Write(state.Bytes, 0, state.Bytes.Length);
                        output.Flush(true);
                    }
                    if (Directory.GetFileSystemEntries(directory, stem + ".*").Length != 2)
                        throw new IOException("The destination changed while importing. Existing files were kept.");
                    File.Move(temporary, destination);
                    created = false;
                    return destination;
                }
                finally { if (created && File.Exists(temporary)) File.Delete(temporary); }
            }
            throw new IOException("No unused savestate filename is available on this card.");
        }
    }
}
