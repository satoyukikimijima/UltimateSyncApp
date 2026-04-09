import xml.etree.ElementTree as ET
import os, json, subprocess, threading, re, sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import winsound  

class UltimateSyncApp:
    def __init__(self, root, batch_file=None):
        self.root = root
        self.is_batch_mode = batch_file is not None
        
        if not self.is_batch_mode:
            self.root.title("EDIUS 4K 究極同期マネージャー V13 (並列処理・超速フルスロットル版)")
            self.root.geometry("1200x900")
            self.root.configure(bg="#2c3e50")

        self.settings_file = batch_file if batch_file else "ultimate_settings_v16.json"
        self.settings = self.load_settings()

        if self.is_batch_mode:
            self.setup_data_only()
            return

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Green.Horizontal.TProgressbar", background='#2ecc71', troughcolor='#34495e')

        main_frame = tk.Frame(root, bg="#2c3e50")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 1. XML設定 ＆ DF/NDF選択
        xml_group = tk.LabelFrame(main_frame, text="1. ATEM XML設定 ＆ プロジェクト設定", fg="white", bg="#34495e", font=("Arial", 10, "bold"))
        xml_group.pack(fill=tk.X, pady=5, padx=5)
        
        self.xml_path = tk.StringVar(value=self.settings.get("xml_path", ""))
        tk.Entry(xml_group, textvariable=self.xml_path, width=100).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(xml_group, text="XML参照", command=self.browse_xml).grid(row=0, column=1, padx=5)

        tc_frame = tk.Frame(xml_group, bg="#34495e")
        tc_frame.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tk.Label(tc_frame, text="タイムコード形式:", bg="#34495e", fg="#f1c40f", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.tc_mode = tk.StringVar(value=self.settings.get("tc_mode", "DF"))
        tk.Radiobutton(tc_frame, text="DF (ドロップフレーム)", variable=self.tc_mode, value="DF", bg="#34495e", fg="white", selectcolor="#2c3e50").pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(tc_frame, text="NDF (ノンドロップフレーム)", variable=self.tc_mode, value="NDF", bg="#34495e", fg="white", selectcolor="#2c3e50").pack(side=tk.LEFT, padx=10)

        # 2. カメラ設定
        cam_group = tk.LabelFrame(main_frame, text="2. カメラ別設定 (先に回した場合は - を入力)", fg="white", bg="#34495e", font=("Arial", 10, "bold"))
        cam_group.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        self.cams = []
        headers = ["カメラ", "ファイル選択・消去 / 選択済みファイル名", "解析情報", "ズレ(±HH:MM:SS:FF)", "結合ファイルの保存先 (別ドライブ指定可)"]
        for i, h in enumerate(headers):
            tk.Label(cam_group, text=h, fg="#ecf0f1", bg="#34495e").grid(row=0, column=i, padx=5, pady=5)

        for i in range(1, 9):
            cam_name = f"CAM {i}"
            row = i + 1
            tk.Label(cam_group, text=cam_name, fg="white", bg="#34495e", font=("Arial", 9, "bold")).grid(row=row, column=0)
            
            f_frame = tk.Frame(cam_group, bg="#34495e")
            f_frame.grid(row=row, column=1, sticky="ew")
            
            files_var = tk.StringVar(value=self.settings.get(f"cam{i}_files", ""))
            display_var = tk.StringVar(value=self.get_basenames(files_var.get()))
            info_var = tk.StringVar(value="---")
            offset_var = tk.StringVar(value=self.settings.get(f"cam{i}_offset", "00:00:00:00"))
            out_var = tk.StringVar(value=self.settings.get(f"cam{i}_out", f"CAM{i}_Joined.MOV"))

            tk.Button(f_frame, text="選択", width=5, command=lambda v=files_var, dv=display_var, idx=i: self.browse_movies(v, dv, idx)).pack(side=tk.LEFT)
            tk.Button(f_frame, text="消去", width=5, bg="#e74c3c", fg="white", command=lambda v=files_var, dv=display_var, iv=info_var, ov=offset_var, idx=i: self.clear_camera(v, dv, iv, ov, idx)).pack(side=tk.LEFT, padx=2)
            tk.Entry(f_frame, textvariable=display_var, width=50, state='readonly', fg="blue", readonlybackground="#ecf0f1").pack(side=tk.LEFT, padx=2)
            
            tk.Label(cam_group, textvariable=info_var, fg="#f1c40f", bg="#34495e").grid(row=row, column=2)
            tk.Entry(cam_group, textvariable=offset_var, width=15, justify='center').grid(row=row, column=3)
            
            out_frame = tk.Frame(cam_group, bg="#34495e")
            out_frame.grid(row=row, column=4, sticky="ew")
            tk.Entry(out_frame, textvariable=out_var, width=28).pack(side=tk.LEFT)
            tk.Button(out_frame, text="変更", width=4, command=lambda v=out_var, idx=i: self.browse_save_as(v, idx)).pack(side=tk.LEFT, padx=2)

            self.cams.append({"files": files_var, "display": display_var, "info": info_var, "offset": offset_var, "out": out_var, "fps": 59.94, "res": "3840x2160"})
            if files_var.get(): self.probe_file(files_var.get().split(";")[0], i-1)

        # 3. XML保存先・進捗
        out_group = tk.LabelFrame(main_frame, text="3. XML出力先 (＆パス指定なし時の結合ファイル保存先)", fg="white", bg="#34495e", font=("Arial", 10, "bold"))
        out_group.pack(fill=tk.X, pady=5, padx=5)
        self.out_dir = tk.StringVar(value=self.settings.get("out_dir", ""))
        tk.Entry(out_group, textvariable=self.out_dir, width=100).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(out_group, text="フォルダ選択", command=self.browse_dir).grid(row=0, column=1, padx=5)

        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100, style="Green.Horizontal.TProgressbar").pack(fill=tk.X, pady=10, padx=5)
        self.status_label = tk.Label(main_frame, text="待機中...", fg="#3498db", bg="#2c3e50", font=("Arial", 12))
        self.status_label.pack()

        btn_frame = tk.Frame(main_frame, bg="#2c3e50")
        btn_frame.pack(pady=10)
        
        tk.Button(btn_frame, text="💾 この設定をバッチ用(JSON)に保存", command=self.save_batch_settings, 
                  bg="#8e44ad", fg="white", font=("Arial", 12, "bold"), height=2, width=30).pack(side=tk.LEFT, padx=10)
        
        tk.Button(btn_frame, text="🚀 通常コンバート開始 (同時並列処理)", command=self.start_process, 
                  bg="#e67e22", fg="white", font=("Arial", 12, "bold"), height=2, width=30).pack(side=tk.LEFT, padx=10)

    def setup_data_only(self):
        class DummyVar:
            def __init__(self, val): self.val = val
            def get(self): return self.val
            
        self.xml_path = DummyVar(self.settings.get("xml_path", ""))
        self.out_dir = DummyVar(self.settings.get("out_dir", ""))
        self.tc_mode = DummyVar(self.settings.get("tc_mode", "DF"))
        self.cams = []
        for i in range(1, 9):
            self.cams.append({
                "files": DummyVar(self.settings.get(f"cam{i}_files", "")),
                "offset": DummyVar(self.settings.get(f"cam{i}_offset", "00:00:00:00")),
                "out": DummyVar(self.settings.get(f"cam{i}_out", f"CAM{i}_Joined.MOV")),
                "fps": 59.94, "res": "3840x2160"
            })

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}

    def save_settings(self):
        data = {"xml_path": self.xml_path.get(), "out_dir": self.out_dir.get(), "tc_mode": self.tc_mode.get()}
        for i, cam in enumerate(self.cams):
            data[f"cam{i+1}_files"] = cam["files"].get(); data[f"cam{i+1}_offset"] = cam["offset"].get(); data[f"cam{i+1}_out"] = cam["out"].get()
        with open(self.settings_file, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)

    def save_batch_settings(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")], title="バッチ用設定ファイルの保存")
        if path:
            self.settings_file = path
            self.save_settings()
            messagebox.showinfo("保存完了", f"バッチ用設定を保存しました:\n{os.path.basename(path)}")
            self.settings_file = "ultimate_settings_v16.json"

    def clear_camera(self, v, dv, iv, ov, idx):
        v.set(""); dv.set("未選択"); iv.set("---"); ov.set("00:00:00:00"); self.cams[idx-1]["out"].set(f"CAM{idx}_Joined.MOV")

    def get_basenames(self, paths_str):
        if not paths_str: return "未選択"
        return ", ".join([os.path.basename(p) for p in paths_str.split(";")])

    def browse_xml(self):
        p = filedialog.askopenfilename(filetypes=[("XML files", "*.xml")])
        if p: self.xml_path.set(p)

    def browse_dir(self):
        p = filedialog.askdirectory()
        if p: self.out_dir.set(p)

    def browse_save_as(self, var, idx):
        default_name = os.path.basename(var.get()) if var.get() else f"CAM{idx}_Joined.MOV"
        p = filedialog.asksaveasfilename(title=f"CAM {idx} の出力先（別ドライブ）を選択", initialfile=default_name, defaultextension=".MOV", filetypes=[("Movie files", "*.MOV;*.mp4")])
        if p: var.set(p)

    def browse_movies(self, var, d_var, idx):
        files = filedialog.askopenfilenames(filetypes=[("Movie files", "*.MOV;*.mp4")])
        if files:
            p = ";".join(files); var.set(p); d_var.set(self.get_basenames(p))
            if not self.is_batch_mode: self.probe_file(files[0], idx-1)

    def probe_file(self, path, cam_idx):
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate', '-of', 'json', path]
            res = subprocess.run(cmd, capture_output=True, text=True)
            info = json.loads(res.stdout)['streams'][0]
            fps = round(eval(info['r_frame_rate']), 2)
            self.cams[cam_idx]["info"].set(f"{info['width']}x{info['height']} / {fps}f")
            self.cams[cam_idx]["fps"] = fps; self.cams[cam_idx]["res"] = f"{info['width']}x{info['height']}"
        except: pass

    def tc_to_frames(self, tc_str, mode):
        is_negative = tc_str.startswith('-')
        clean_tc = tc_str.lstrip('-')
        try:
            h, m, s, f = map(int, clean_tc.split(':'))
            total_minutes = h * 60 + m
            total_frames = (total_minutes * 60 + s) * 60 + f
            if mode == "DF":
                drop_count = 4 * (total_minutes - (total_minutes // 10))
                frames = total_frames - drop_count
            else:
                frames = total_frames 
            return -frames if is_negative else frames
        except: return 0

    def start_process(self):
        self.save_settings()
        threading.Thread(target=self.process_task, daemon=True).start()

    def process_task(self):
        out_dir = self.out_dir.get()
        if out_dir and not os.path.exists(out_dir): os.makedirs(out_dir, exist_ok=True)
        
        tc_mode = self.tc_mode.get()
        synced_map = {}
        active_cams = [(i, c) for i, c in enumerate(self.cams) if c["files"].get()]
        total_cams = len(active_cams)
        
        if total_cams == 0: return

        # ★V13 並列処理の準備
        completed_cams = [0]
        lock = threading.Lock()
        threads = []

        msg = f"全 {total_cams} 台のカメラを同時並列で連結中... (超速モード)"
        if not self.is_batch_mode: self.status_label.config(text=msg)
        print(msg)

        # ★各カメラごとの連結処理関数
        def run_concat(i, cam, output_path, file_list, offset_frames):
            if not os.path.exists(output_path):
                # 複数同時にテキストファイルを作るため、名前が被らないようにする
                list_file = f"list_cam{i+1}_{threading.get_ident()}.txt"
                with open(list_file, "w", encoding="utf-8") as f:
                    for m in file_list: f.write(f"file '{m}'\n")
                
                subprocess.run(['ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', '-y', output_path], shell=True)
                if os.path.exists(list_file): os.remove(list_file)

            base_segment = 1
            match = re.search(r'[ _](\d{2})(?:\.[a-zA-Z0-9]+)?\s*$', file_list[0])
            if match:
                base_segment = int(match.group(1))

            # ロックをかけて安全に辞書と進捗バーを更新
            with lock:
                synced_map[f"CAM {i+1}"] = {
                    "path": output_path,
                    "offset": offset_frames,
                    "w": cam["res"].split('x')[0],
                    "h": cam["res"].split('x')[1],
                    "base_seg": base_segment
                }
                completed_cams[0] += 1
                if not self.is_batch_mode:
                    self.progress_var.set((completed_cams[0] / total_cams) * 80)
                print(f"CAM {i+1} 完了！ ({completed_cams[0]}/{total_cams})")

        # 全カメラの処理を同時に一斉スタート！
        for i, cam in active_cams:
            file_list = cam["files"].get().split(";")
            output_name = cam["out"].get()
            if os.path.isabs(output_name): output_path = output_name
            else: output_path = os.path.join(out_dir, output_name)
                
            out_file_dir = os.path.dirname(output_path)
            if out_file_dir and not os.path.exists(out_file_dir):
                os.makedirs(out_file_dir, exist_ok=True)

            offset_frames = self.tc_to_frames(cam["offset"].get(), tc_mode)
            
            t = threading.Thread(target=run_concat, args=(i, cam, output_path, file_list, offset_frames))
            threads.append(t)
            t.start()

        # すべてのカメラの処理が終わるのを裏で待つ
        for t in threads:
            t.join()

        msg2 = f"XMLの同期情報を精密計算＆マルチトラック構築中... ({tc_mode}モード)"
        if not self.is_batch_mode: self.status_label.config(text=msg2)
        print(msg2)
        
        self.convert_xml(synced_map, tc_mode)
        
        if not self.is_batch_mode:
            self.progress_var.set(100)
            self.status_label.config(text="✨ 超速・マルチトラック完全同期完了！✨", fg="#2ecc71")
            self.show_flashy_success()
        else:
            print("✨ 処理完了 ✨")

    def convert_xml(self, synced_map, tc_mode):
        tree = ET.parse(self.xml_path.get()); root = tree.getroot()
        
        for df_tag in root.iter('displayformat'):
            df_tag.text = tc_mode
        
        SPLIT_DURATION_FRAMES = 0 
        for clip in root.iter('clipitem'):
            f_name_tag = clip.find('.//file/name')
            if f_name_tag is not None and f_name_tag.text:
                if re.search(r'[ _]02(?:\.[a-zA-Z0-9]+)?\s*$', f_name_tag.text, re.IGNORECASE):
                    start_el = clip.find('start'); in_el = clip.find('in')
                    if start_el is not None and in_el is not None:
                        try:
                            calc_val = int(start_el.text) - int(in_el.text)
                            if calc_val > 0:
                                SPLIT_DURATION_FRAMES = calc_val
                                break 
                        except: pass
        
        if SPLIT_DURATION_FRAMES == 0: SPLIT_DURATION_FRAMES = 376920 

        for elem in root.iter():
            for child in list(elem):
                if child.tag in ['audio', 'link']:
                    elem.remove(child)

        camera_tracks = {f"CAM {i}": [] for i in range(1, 9)}
        other_clips = []

        video_node = root.find('.//media/video')
        if video_node is not None:
            old_tracks = video_node.findall('track')
            all_clips = []
            for t in old_tracks:
                all_clips.extend(t.findall('clipitem'))
                video_node.remove(t)

            cam_base_segments = {}
            for clip in all_clips:
                name_el = clip.find('name')
                if name_el is not None and name_el.text:
                    match = re.search(r'[ _](\d{2})(?:\.[a-zA-Z0-9]+)?\s*$', name_el.text)
                    if match:
                        seg = int(match.group(1))
                        for cam_key in synced_map.keys():
                            if cam_key in name_el.text:
                                if cam_key not in cam_base_segments or seg < cam_base_segments[cam_key]:
                                    cam_base_segments[cam_key] = seg

            for clip in all_clips:
                name_el = clip.find('name')
                if name_el is None:
                    other_clips.append(clip); continue

                matched_cam = None
                for cam_key, data in synced_map.items():
                    if cam_key in name_el.text:
                        matched_cam = cam_key; break

                if matched_cam:
                    file_el = clip.find('file')
                    if file_el is None: continue 
                    f_name_tag = file_el.find('name')
                    
                    base_seg = cam_base_segments.get(matched_cam, 1)
                    clip_seg = base_seg
                    match = re.search(r'[ _](\d{2})(?:\.[a-zA-Z0-9]+)?\s*$', name_el.text)
                    if match: clip_seg = int(match.group(1))

                    relative_seg = max(0, clip_seg - base_seg)
                    shift_amount = (relative_seg * SPLIT_DURATION_FRAMES) - data["offset"]
                    
                    sample = clip.find('.//samplecharacteristics')
                    if sample is not None: 
                        sample.find('width').text = data["w"]; sample.find('height').text = data["h"]
                    
                    for dur_tag in clip.iter('duration'): dur_tag.text = "2000000"

                    for tag in ['in', 'out', 'start', 'end']:
                        el = clip.find(tag)
                        if el is not None and int(el.text) >= 0:
                            orig_val = int(el.text)
                            if tag in ['in', 'out']: el.text = str(max(0, orig_val + shift_amount))

                    new_name = os.path.basename(data["path"])
                    file_el.set('id', new_name + "_4K")
                    if f_name_tag is not None: f_name_tag.text = new_name
                    path_tag = file_el.find('pathurl')
                    if path_tag is not None:
                        path_tag.text = "file://localhost/" + os.path.abspath(data["path"]).replace("\\", "/").replace(":", "%3A")
                    
                    camera_tracks[matched_cam].append(clip)
                else:
                    other_clips.append(clip)

            for i in range(1, 9):
                cam_key = f"CAM {i}"
                if camera_tracks[cam_key]:
                    def get_start(c):
                        s = c.find('start')
                        if s is not None and s.text:
                            try: return int(s.text)
                            except: return 0
                        return 0
                    
                    camera_tracks[cam_key].sort(key=get_start)
                    unique_clips = []; seen_starts = set()
                    
                    for c in camera_tracks[cam_key]:
                        start_val = get_start(c)
                        if start_val not in seen_starts:
                            seen_starts.add(start_val)
                            unique_clips.append(c)

                    for idx in range(len(unique_clips) - 1):
                        curr_clip = unique_clips[idx]
                        next_clip = unique_clips[idx + 1]
                        
                        curr_end_el = curr_clip.find('end')
                        next_start_el = next_clip.find('start')
                        
                        if curr_end_el is not None and next_start_el is not None:
                            curr_end = int(curr_end_el.text)
                            next_start = int(next_start_el.text)
                            if curr_end > next_start:
                                curr_end_el.text = str(next_start)
                                curr_in_el = curr_clip.find('in')
                                curr_out_el = curr_clip.find('out')
                                curr_start_el = curr_clip.find('start')
                                if curr_in_el is not None and curr_out_el is not None and curr_start_el is not None:
                                    curr_in = int(curr_in_el.text)
                                    curr_start = int(curr_start_el.text)
                                    new_duration = next_start - curr_start
                                    curr_out_el.text = str(curr_in + new_duration)

                    new_track = ET.SubElement(video_node, 'track')
                    for c in unique_clips: new_track.append(c)
                    
                    ET.SubElement(new_track, 'enabled').text = 'TRUE'
                    ET.SubElement(new_track, 'locked').text = 'FALSE'
            
            if other_clips:
                new_track = ET.SubElement(video_node, 'track')
                for c in other_clips: new_track.append(c)
                ET.SubElement(new_track, 'enabled').text = 'TRUE'
                ET.SubElement(new_track, 'locked').text = 'FALSE'

        output_xml = os.path.join(self.out_dir.get(), "EDIUS_ULTIMATE_MULTITRACK_SYNC.xml")
        with open(output_xml, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n')
            tree.write(f, encoding='utf-8', xml_declaration=False)

    def show_flashy_success(self):
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        top = tk.Toplevel(self.root); top.title("祝・超速完了！"); top.geometry("600x350"); top.configure(bg="#f1c40f")
        tk.Label(top, text="🎉 超速・並列コンバート完了！ 🎉", font=("Arial", 22, "bold"), bg="#f1c40f", fg="#c0392b").pack(pady=20)
        tk.Label(top, text="すべてのカメラを同時に連結する「マルチスレッド処理」により、\n待ち時間を極限まで削ぎ落としました。\n\n複数SSDへの書き出しと組み合わせれば、まさに無敵のワークフローです！", 
                 font=("Arial", 12), bg="#f1c40f", fg="#2c3e50").pack(pady=10)
        tk.Button(top, text="意気揚々と閉じる", command=top.destroy, font=("Arial", 12, "bold"), width=20, height=2).pack(pady=20)

if __name__ == "__main__":
    root = tk.Tk()
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
        print(f"========== バッチ処理開始: {json_file} ==========")
        root.withdraw() 
        app = UltimateSyncApp(root, batch_file=json_file)
        app.process_task() 
        print(f"========== バッチ処理完了: {json_file} ==========\n")
        root.destroy()
    else:
        app = UltimateSyncApp(root)
        root.mainloop()