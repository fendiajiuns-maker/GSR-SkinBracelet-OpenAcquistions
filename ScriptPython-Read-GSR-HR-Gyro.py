import tkinter as tk
from tkinter import ttk, messagebox
import threading
import datetime
import os
import csv
import time
import serial
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# === KONFIGURASI ===
DEFAULT_COM = "COM8"
BAUDRATE = 115200
FOLDER = "SensorData"
DURATION_SECONDS = 60
OUTPUT_INTERVAL = 0.1  # data rate optimal

def parse_sensor_packet(packet: bytes):
    if len(packet) != 19 or packet[0] != 0xFA or packet[-1] != 0xAF:
        return None
    checksum = sum(packet[1:17]) & 0xFF
    if checksum != packet[17]:
        return None
    gsr = (packet[1] << 8) | packet[2]
    gyro_x = (packet[3] << 8) | packet[4]
    gyro_y = (packet[5] << 8) | packet[6]
    gyro_z = (packet[7] << 8) | packet[8]
    hr = packet[15]
    return datetime.datetime.now(), gsr, hr, gyro_x, gyro_y, gyro_z

class SensorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Sensor Recorder GUI")
        self.root.geometry("700x700")
        self.root.configure(bg="white")

        self.stop_event = threading.Event()
        self.thread = None
        self.hr_data = []
        self.gsr_data = []

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def build_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)

        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="x")

        ttk.Label(frame, text="Nama Peserta:").grid(row=0, column=0, padx=5, sticky="e")
        self.name_entry = ttk.Entry(frame, width=25)
        self.name_entry.grid(row=0, column=1)

        ttk.Label(frame, text="Port COM:").grid(row=0, column=2, padx=5, sticky="e")
        self.com_entry = ttk.Entry(frame, width=10)
        self.com_entry.insert(0, DEFAULT_COM)
        self.com_entry.grid(row=0, column=3)

        self.start_btn = ttk.Button(frame, text="Mulai Rekam", command=self.start_recording)
        self.start_btn.grid(row=0, column=4, padx=10)

        self.stop_btn = ttk.Button(frame, text="Hentikan", command=self.stop_recording, state="disabled")
        self.stop_btn.grid(row=0, column=5)

        self.status_label = ttk.Label(self.root, text="Status: Menunggu...", font=('Segoe UI', 10, 'bold'))
        self.status_label.pack(pady=10)

        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack()

        self.debug_label = tk.Label(self.root, text="", font=("Consolas", 9),
                                    justify="left", anchor="w", bg="#f7f7f7", fg="#444", width=60)
        self.debug_label.pack(pady=10, fill="x")

    def start_recording(self):
        name = self.name_entry.get().strip()
        com_port = self.com_entry.get().strip() or DEFAULT_COM

        if not name:
            messagebox.showerror("Error", "Nama peserta harus diisi.")
            return

        self.status_label.config(text="Status: Perekaman berjalan...")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.record_sensor, args=(name, com_port), daemon=True)
        self.thread.start()

    def stop_recording(self):
        self.status_label.config(text="Status: Menghentikan...")
        self.stop_event.set()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def record_sensor(self, name, com_port):
        try:
            ser = serial.Serial(com_port, BAUDRATE, timeout=1)
        except Exception as e:
            self.debug_label.config(text=f"Gagal membuka {com_port}:\n{e}")
            return

        folder_path = os.path.join(FOLDER, name)
        os.makedirs(folder_path, exist_ok=True)
        file_index = 1
        start_time = datetime.datetime.now()

        def new_file(index):
            filepath = os.path.join(folder_path, f"{name}_{index}.csv")
            f = open(filepath, 'w', newline='')
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "GSR", "HR", "GyroX", "GyroY", "GyroZ"])
            return f, writer

        file, writer = new_file(file_index)
        buffer = b""

        while not self.stop_event.is_set():
            try:
                buffer += ser.read(ser.in_waiting or 1)
                while len(buffer) >= 19:
                    if buffer[0] == 0xFA and buffer[18] == 0xAF:
                        packet = buffer[:19]
                        result = parse_sensor_packet(packet)
                        if result:
                            ts, gsr, hr, gx, gy, gz = result
                            writer.writerow([ts.strftime("%Y-%m-%d %H:%M:%S.%f"), gsr, hr, gx, gy, gz])
                            self.hr_data.append(hr)
                            self.gsr_data.append(gsr)
                            self.update_chart()
                            if self.debug_label.winfo_exists():
                                self.debug_label.config(text=f"GSR: {gsr} | HR: {hr} | Gyro: {gx}, {gy}, {gz}")
                        buffer = buffer[19:]
                    else:
                        buffer = buffer[1:]

                if (datetime.datetime.now() - start_time).total_seconds() > DURATION_SECONDS:
                    file.close()
                    file_index += 1
                    file, writer = new_file(file_index)
                    start_time = datetime.datetime.now()
            except Exception as e:
                print(f"❗ Error membaca: {e}")
                break
            time.sleep(OUTPUT_INTERVAL)

        file.close()
        ser.close()
        try:
            if self.status_label.winfo_exists():
                self.status_label.config(text="Status: Rekaman selesai.")
        except Exception as e:
            print(f"❗ GUI sudah ditutup: {e}")

    def update_chart(self):
        self.ax.clear()
        self.ax.plot(self.hr_data[-50:], label="HR", color="red")
        self.ax.plot(self.gsr_data[-50:], label="GSR", color="orange")
        self.ax.set_title("Sensor Real-Time")
        self.ax.legend()
        self.canvas.draw()

    def on_closing(self):
        self.stop_event.set()
        time.sleep(0.2)
        self.root.destroy()

# === Mulai Aplikasi ===
if __name__ == "__main__":
    root = tk.Tk()
    app = SensorGUI(root)
    root.mainloop()