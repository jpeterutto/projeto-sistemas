package com.chat;

import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;
import com.chat.proto.ChatProtos.Message;
import com.chat.proto.ChatProtos.Message.Type;

import java.time.Instant;
import java.util.List;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.concurrent.CopyOnWriteArrayList;

public class ClientBot {
    private static final String SENDER = System.getenv("BOT_NAME") != null ? System.getenv("BOT_NAME") : "bot_default";
    private static final String BROKER_URL = System.getenv("BROKER_URL") != null ? System.getenv("BROKER_URL") : "tcp://broker:5555";
    private static final String PUBSUB_URL = System.getenv("PUBSUB_URL") != null ? System.getenv("PUBSUB_URL") : "tcp://pubsub:5558";

    private static CopyOnWriteArrayList<String> subscribedChannels = new CopyOnWriteArrayList<>();

    public static void main(String[] args) {
        System.out.println("Iniciando client: " + SENDER);
        
        Thread subThread = new Thread(() -> {
            try (ZContext subContext = new ZContext()) {
                ZMQ.Socket subSocket = subContext.createSocket(SocketType.SUB);
                subSocket.connect(PUBSUB_URL);
                int subCount = 0;
                
                while (!Thread.currentThread().isInterrupted()) {
                    while (subCount < subscribedChannels.size()) {
                        String newCh = subscribedChannels.get(subCount);
                        subSocket.subscribe(newCh.getBytes(ZMQ.CHARSET));
                        subCount++;
                        System.out.printf("[%s] CLIENT %s | INSCRITO (SUBSCRIBE ok) no topico: %s%n", Instant.now().toString(), SENDER, newCh);
                    }
                    
                    byte[] topic = subSocket.recv(ZMQ.DONTWAIT);
                    if (topic != null) {
                        byte[] payload = subSocket.recv(0);
                        try {
                            Message evt = Message.parseFrom(payload);
                            if (evt.getType() == Type.CHANNEL_MESSAGE_EVENT) {
                                String ts = Instant.now().toString();
                                System.out.printf("[%s] CLIENT %s | RECEBIDA >> Canal: %s | Por: %s | Texto: '%s' | [TsEnvio: %s] | [TsRecebimento: %s]%n", 
                                    ts, SENDER, evt.getChannelEvent().getChannelName(), evt.getChannelEvent().getSender(), evt.getChannelEvent().getText(), evt.getTimestamp(), ts);
                            }
                        } catch(Exception e) { e.printStackTrace(); }
                    } else {
                        try { Thread.sleep(50); } catch(Exception e) {}
                    }
                }
            }
        });
        subThread.setDaemon(true);
        subThread.start();
        
        try (ZContext context = new ZContext()) {
            ZMQ.Socket socket = context.createSocket(SocketType.REQ);
            socket.connect(BROKER_URL);
            
            try { Thread.sleep(3000); } catch (Exception e){}
            
            boolean loggedIn = false;
            while (!loggedIn) {
                Message loginReq = Message.newBuilder()
                    .setType(Type.LOGIN_REQ)
                    .setTimestamp(Instant.now().toString())
                    .setSender(SENDER)
                    .setLoginReq(Message.LoginRequest.newBuilder().setUsername(SENDER).build())
                    .build();
                
                logMessage("out", "broker", "LOGIN_REQ", "user=" + SENDER, "");
                socket.send(loginReq.toByteArray(), 0);
                
                byte[] reply = socket.recv(0);
                Message repMessage = Message.parseFrom(reply);
                
                boolean success = repMessage.getLoginRep().getSuccess();
                String resultStr = success ? "OK" : "ERROR";
                logMessage("in", repMessage.getSender(), "LOGIN_REP", "status=" + resultStr, resultStr);
                
                if (success) {
                    loggedIn = true;
                } else {
                    System.out.println("Erro de login. Retentando em 5s...");
                    try { Thread.sleep(5000); } catch (Exception e){}
                }
            }
            
            while (true) {
                Message listReq = Message.newBuilder()
                    .setType(Type.LIST_CHANNELS_REQ)
                    .setTimestamp(Instant.now().toString())
                    .setSender(SENDER)
                    .setListReq(Message.ListChannelsRequest.newBuilder().build())
                    .build();
                
                logMessage("out", "broker", "LIST_CHANNELS_REQ", "", "");
                socket.send(listReq.toByteArray(), 0);
                
                byte[] listReply = socket.recv(0);
                Message listRepMessage = Message.parseFrom(listReply);
                List<String> availableChannels = new ArrayList<>(listRepMessage.getListRep().getChannelsList());
                logMessage("in", listRepMessage.getSender(), "LIST_CHANNELS_REP", "channels=" + availableChannels, "OK");
                
                if (availableChannels.size() < 5) {
                    String newChName = "#bot_canal_" + Instant.now().toEpochMilli();
                    Message createReq = Message.newBuilder()
                        .setType(Type.CREATE_CHANNEL_REQ)
                        .setTimestamp(Instant.now().toString())
                        .setSender(SENDER)
                        .setCreateReq(Message.CreateChannelRequest.newBuilder().setChannelName(newChName).build())
                        .build();
                    
                    logMessage("out", "broker", "CREATE_CHANNEL_REQ", "channel=" + newChName, "");
                    socket.send(createReq.toByteArray(), 0);
                    
                    byte[] createReply = socket.recv(0);
                    Message createRepMessage = Message.parseFrom(createReply);
                    boolean success = createRepMessage.getCreateRep().getSuccess();
                    logMessage("in", createRepMessage.getSender(), "CREATE_CHANNEL_REP", "channel=" + newChName, success ? "OK" : "ERROR");
                    if (success) {
                        availableChannels.add(newChName);
                    }
                }
                
                if (subscribedChannels.size() < 3 && availableChannels.size() > 0) {
                    List<String> notSubscribed = new ArrayList<>(availableChannels);
                    notSubscribed.removeAll(subscribedChannels);
                    
                    if (!notSubscribed.isEmpty()) {
                        String randomChannel = notSubscribed.get((int) (Math.random() * notSubscribed.size()));
                        subscribedChannels.add(randomChannel);
                    }
                }
                
                String targetChannel = null;
                if (!subscribedChannels.isEmpty()) {
                    targetChannel = subscribedChannels.get((int)(Math.random() * subscribedChannels.size()));
                } else if (!availableChannels.isEmpty()) {
                    targetChannel = availableChannels.get((int)(Math.random() * availableChannels.size()));
                }
                
                if (targetChannel != null) {
                    for (int i=1; i<=10; i++) {
                        String text = "Msg automatica (ciclo P2) msg " + i + " de " + SENDER;
                        Message pubReq = Message.newBuilder()
                            .setType(Type.PUBLISH_MESSAGE_REQ)
                            .setTimestamp(Instant.now().toString())
                            .setSender(SENDER)
                            .setPubReq(Message.PublishMessageRequest.newBuilder().setChannelName(targetChannel).setText(text).build())
                            .build();
                            
                        logMessage("out", "broker", "PUBLISH_MESSAGE_REQ", "channel=" + targetChannel, "");
                        socket.send(pubReq.toByteArray(), 0);
                        
                        byte[] pubReply = socket.recv(0);
                        Message pubRepMessage = Message.parseFrom(pubReply);
                        boolean ok = pubRepMessage.getPubRep().getSuccess();
                        logMessage("in", pubRepMessage.getSender(), "PUBLISH_MESSAGE_REP", "channel=" + targetChannel, ok ? "OK" : "ERROR");
                        
                        try { Thread.sleep(1000); } catch(Exception e) {}
                    }
                } else {
                    try { Thread.sleep(2000); } catch(Exception e) {}
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private static void logMessage(String direction, String target, String msgType, String content, String result) {
        String ts = Instant.now().toString();
        String resStr = result.isEmpty() ? "" : " | result=" + result;
        if (direction.equals("in")) {
            System.out.printf("[%s] SERVER %s -> CLIENT %s | %s | %s%s%n", ts, target, SENDER, msgType, content, resStr);
        } else {
            System.out.printf("[%s] CLIENT %s -> SERVER %s | %s | %s%s%n", ts, SENDER, target, msgType, content, resStr);
        }
    }
}
