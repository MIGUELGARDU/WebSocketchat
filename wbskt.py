#!/usr/bin/env python

import pathlib,ssl,asyncio,json,logging,websockets,random, string,time, psycopg2, smtplib
from email.mime.text import MIMEText
from datetime import datetime, date,timedelta
import ast

class Sockets:
	def __init__(self):
		logging.basicConfig()
		self.conexion = set()
		self.usuarios  = {}
		self.usuarios_soporte = {}
		self.chats = {}
		self.caracteres = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
		try :
			connection = psycopg2.connect( user = "usuario",
							password = "contrasena",
							host = "127.0.0.1",
							port = "5432",
							database = "db")
			connection.autocommit = True
			self.cursor = connection.cursor()
		except Exception as e:
			print(e)
		start_server = websockets.serve(self.soporte, "localhost", 6789)
		asyncio.get_event_loop().run_until_complete(start_server)
		asyncio.get_event_loop().run_forever()

	async def crearChat(self,id_chat,id_usuario,proyecto):
		fecha = time.strftime("%Y_%m_%d")
		hora = time.strftime("%H:%M:%S")
		if not id_chat in self.chats:
			self.chats[id_chat] = {"usuario":id_usuario,
						"id_soporte":"",
						"proyecto":proyecto,
						"mensajes":list(),
						"hora_inicio":hora,
						"fecha_inicio":fecha}
	async def historial(self, id_chat,socket):
		#print("historial")
		hoy = datetime.now().strftime("%Y_%m_%d")
		historico = (datetime.now()-timedelta(days=2)).strftime("%Y_%m_%d")
		self.cursor.execute("select id_chat from admin.chats")
		chats_db = self.cursor.fetchall()
		##print (chats_db)
		fechas = ""
		history_db = {}
		listadechats = list()
		if [s for s in chats_db if id_chat in s]:
			self.cursor.execute("select * from admin.chats where id_chat=\'%s\' and fecha_inicio between \'%s\' and \'%s\'"%(id_chat,historico,hoy))
			fechas = self.cursor.fetchall()
		##print (fechas)
		if fechas:
			fecha1 = fechas[0][2]
			for fecha in fechas:
				if fecha1 != fecha[2]:
					listadechats = list()
					fecha1 = fecha[2]
				#print (fecha[0])
				for i in json.loads(fecha[4]):
					listadechats.append(i)
					history_db[fecha1.strftime("%Y-%m-%d")]=listadechats
			await socket.send(json.dumps({"action":"historial",
                                                           "id_chat":id_chat,
                                                           "listmensajes":history_db,
                                                           "proyecto":self.chats[id_chat]["proyecto"]}))



	async def escribirchat(self, id_chat, id_user, tipo, mensaje, proyecto):
		fecha = time.strftime("%Y_%m_%d")
		hora = time.strftime("%H:%M:%S")
		if tipo == "servidor":
			self.chats[id_chat]["mensajes"].append([fecha,hora,mensaje,"servidor",""])
			await self.usuarios[self.chats[id_chat]["usuario"]][proyecto]["websocket"].send(json.dumps({"action":"mensaje",
														"id_chat":id_chat,
														"nombre":"servidor",
														"mensaje":mensaje}))
		elif tipo == "soporte":
			if not self.chats[id_chat]["id_soporte"]:
				for i in self.usuarios_soporte:
					self.chats[id_chat]["id_soporte"]=id_user
					await self.usuarios_soporte[i]["soporte"]["websocket"].send(json.dumps({"action":"remove_chat","id_chat":id_chat,"id_soporte":id_user}))
				await self.historial(id_chat,self.usuarios_soporte[id_user]["soporte"]["websocket"])
			self.chats[id_chat]["mensajes"].append([fecha,hora,mensaje,self.usuarios_soporte[id_user]["soporte"]["nombre"],id_user])
			await self.usuarios[self.chats[id_chat]["usuario"]][proyecto]["websocket"].send(json.dumps({"action":"mensaje",
														"id_chat":id_chat,
														"tipo":tipo,
														"nombre":self.usuarios_soporte[id_user]["soporte"]["nombre"],
														"mensaje":mensaje}))
		elif tipo == "usuario":
			if self.chats[id_chat]["id_soporte"]:
				self.chats[id_chat]["mensajes"].append([fecha,hora,mensaje,self.usuarios[id_user][proyecto]["nombre"],id_user])
				await self.usuarios_soporte[self.chats[id_chat]["id_soporte"]]["soporte"]["websocket"].send(json.dumps({"action":"mensaje",
															"id_chat":id_chat,
															"tipo":tipo,
															"mensaje":mensaje,
															"nombre":self.usuarios[id_user][proyecto]["nombre"],
															"proyecto":proyecto}))
			else:
				self.chats[id_chat]["mensajes"].append([fecha,hora,mensaje,self.usuarios[id_user][proyecto]["nombre"],id_user])
				if len(self.usuarios_soporte) > 0:
					for i in self.usuarios_soporte:
						await self.usuarios_soporte[i]["soporte"]["websocket"].send(json.dumps({"action":"mensaje",
															"tipo":tipo,
															"id_chat":id_chat,
															"nombre":self.usuarios[id_user][proyecto]["nombre"],
															"proyecto":proyecto,
															"mensaje":mensaje}))
				else:
					await self.mandar_correo({"nombre":self.usuarios[id_user][proyecto]["nombre"],"mensaje":mensaje})
		##print(self.chats[id_chat]["mensajes"])

	async def terminarchat(self, id_chat, id_user, tipo, proyecto):
		fecha = time.strftime("%Y_%m_%d")
		hora = time.strftime("%H:%M:%S")
		if id_chat:
			if self.chats[id_chat]["id_soporte"]:
				await self.usuarios_soporte[self.chats[id_chat]["id_soporte"]]["soporte"]["websocket"].send(json.dumps({"action":"desconectado",
															"id_chat":id_chat,
                	                                                                                                 "nombre":self.usuarios[id_user][proyecto]["nombre"],
                        	                                                                                         "proyecto":proyecto}))
			else:
				for i in self.usuarios_soporte:
					await self.usuarios_soporte[i]["soporte"]["websocket"].send(json.dumps({"action":"desconectado",
																"id_chat":id_chat,
                		                                                                                                 "nombre":self.usuarios[id_user][proyecto]["nombre"],
                	        	                                                                                         "proyecto":proyecto}))


			self.chats[id_chat]["mensajes"].append([fecha,hora,"Desconectado",self.usuarios[id_user][proyecto]["nombre"],id_user])
			await self.guardarendb(id_chat)



	async def guardarendb(self, id_chat):
		id_user = self.chats[id_chat]["usuario"]
		mensajes = str(self.chats[id_chat]["mensajes"]).replace("\'","\"")
		fecha_inicio = self.chats[id_chat]["fecha_inicio"]
		hora_inicio = self.chats[id_chat]["hora_inicio"]
		print ("guardando")
		try:
			if len(mensajes)>0:
				print("insertando")
				print("insert into admin.chats(id_usuario, mensajes, fecha_inicio, hora_inicio, id_chat) values(%s,\'%s\',\'%s\',\'%s\',\'%s\')"%(id_user,str(mensajes), fecha_inicio, hora_inicio,id_chat))
				codigo = self.cursor.execute("insert into admin.chats(id_usuario, mensajes, fecha_inicio, hora_inicio, id_chat) values(%s,\'%s\',\'%s\',\'%s\',\'%s\')"%(id_user,str(mensajes), fecha_inicio, hora_inicio,id_chat))
				print(codigo)
			del self.chats[id_chat]
		except Exception as e:
			print (e)

	async def conectados(self, websocket):
		self.conexion.add(websocket)

	async def registro(self, data, websocket):
		tipo = data["tipo"]
		proyecto = data["proyecto"]
		id = data["id"]
		nombre = data["nombre"]
		if tipo == "usuario":
		##	try:
			id_chat = proyecto+str(id)
			await self.crearChat(id_chat,id,proyecto)
			self.usuarios[id]={}
			self.usuarios[id][proyecto]={"id_chat":id_chat, "websocket":websocket, "nombre":nombre}
			##print ("ANtes de historial")
			await self.historial(id_chat,websocket)
			##print("Despues de historial")
			await self.escribirchat(id_chat, id, "servidor", "Hola %s ¿En que te puedo ayudar?" %nombre, proyecto)
		#	except Exception as e:
		#		print(e)
		elif tipo ==  "soporte":
			self.usuarios_soporte[id]={}
			self.usuarios_soporte[id]["soporte"]={"websocket":websocket,"nombre":nombre}
			for id_chat in self.chats:
				if not self.chats[id_chat]["id_soporte"]:
					for mensaje in self.chats[id_chat]["mensajes"]:
						if mensaje[4]:
							await websocket.send(json.dumps({"action":"mensaje",
										"id_chat":id_chat,
										"nombre":mensaje[3],
										"proyecto":self.chats[id_chat]["proyecto"],
										"mensaje":mensaje[2]}))

	async def unregister(self,data, websocket):
		fecha = time.strftime("%Y_%m_%d")
		hora = time.strftime("%H:%M:%S")
		tipo = data["tipo"]
		id = data["id"]
		id_chat= data["id_chat"]
		proyecto = data["proyecto"]
		if tipo == "usuario":
			await self.terminarchat(id_chat, id, tipo, proyecto)
			del self.usuarios[id][proyecto]
			if not len(self.usuarios[id]):
				del self.usuarios[id]
		if tipo == "soporte":
			for idch in self.chats:
				if id == self.chats[idch]["id_soporte"]:
					self.chats[idch]["id_soporte"]=""
					for i in self.usuarios_soporte:
						mensaje = "El usuario de soporte %s dejo a %s"%(self.usuarios_soporte[id]["soporte"]["nombre"],
									self.usuarios[self.chats[idch]["usuario"]][self.chats[idch]["proyecto"]]["nombre"])
						await self.usuarios_soporte[i]["soporte"]["websocket"].send(json.dumps({"action":"mensaje",
															"id_chat":idch,
															"mensaje":mensaje,
															"nombre":self.usuarios[self.chats[idch]["usuario"]][self.chats[idch]["proyecto"]]["nombre"],
															"proyecto":self.chats[idch]["proyecto"]}))
						self.chats[idch]["mensajes"].append([fecha,
											hora,
											mensaje,
											self.usuarios_soporte[id]["soporte"]["nombre"],
											id])

			del self.usuarios_soporte[id]
		self.conexion.remove(websocket)
		await websocket.close()

	async def mandar_correo(self, data):
		self.s = smtplib.SMTP('smtp.gmail.com',587)
		self.s.ehlo()
		self.s.starttls()
		self.sender = 'correo@gmail.com'
		self.sender_pssw = "pssw"
		self.s.login(self.sender,self.sender_pssw)
		self.recipients = ['correos']
		nombre_usuario = data["nombre"]
		mensaje = data["mensaje"]
		msg = MIMEText("Aviso \nEL usuario %s mando un chat %s y no hay usuarios tipo soporte conectados"%(nombre_usuario,mensaje))
		msg['Subject']="Aviso de chat"
		msg['From']=self.sender
		msg['To']=", ".join(self.recipients)
		self.s.sendmail(self.sender, self.recipients, msg.as_string())
		self.s.close()

	async def lost_connection(self, websocket):
		data = ""
		for id in self.usuarios:
			for proyecto in self.usuarios[id]:
				if websocket == self.usuarios[id][proyecto]["websocket"]:
					data = {"id":id,
						"id_chat":self.usuarios[id][proyecto]["id_chat"],
						"proyecto":proyecto,
						"tipo":"usuario"}
					break
		if not data:
			for id in self.usuarios_soporte:
				if websocket == self.usuarios_soporte[id]["soporte"]["websocket"]:
					data = {"id":id,
						"id_chat":"",
						"proyecto":"soporte",
						"tipo":"soporte"}
					break
		if data:
			await self.unregister(data,websocket)
		else:
			self.conexion.remove(websocket)


	async def message(self, data, websocket):
		id_chat = data["id_chat"]
		id = data["id"]
		proyecto = data["proyecto"]
		tipo = data["tipo"]
		mensaje =data["mensaje"]
		await self.escribirchat(id_chat, id, tipo, mensaje, proyecto)

	async def soporte(self, websocket, path):
		try:
			async for message in websocket:
				sijson = True
				try:
					data = json.loads(message)
				except:
					sijson =False
				if sijson:
					#print (data)
					if data["action"] == "register":
						await self.registro(data, websocket)
						await self.conectados(websocket)
					elif data["action"] == "unregister":
						await self.unregister(data, websocket)
					elif data["action"] == "message":
						await self.message(data, websocket)
					else:
						await websocket.send("Error action no identificado")
				else:
						await websocket.send("Error el socket solo admite json")
		except Exception as e:
			if websocket in self.conexion:
				await self.lost_connection(websocket)
